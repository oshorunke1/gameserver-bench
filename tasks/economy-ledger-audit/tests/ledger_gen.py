"""Hidden log generator for the ledger audit task.

It builds a messy event log one record at a time, in seq order, and keeps
its own running books as it goes so it knows the right answer at the end.
After that it scrambles the file order and sprinkles in duplicate lines,
which should not change the answer at all.
"""

import json
import math
import random

MAX_TX = 1_000_000
CAP = 10_000_000

PLAYER_TYPES = {"spend", "purchase", "refund", "trade"}


def _amount_kind(value, is_trade):
    # sort an amount into ok, severe or minor
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "minor"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or value < 0 or value > MAX_TX:
            return "severe"
        return "minor"
    if value < 0 or value > MAX_TX:
        return "severe"
    if value == 0:
        return "ok" if is_trade else "minor"
    return "ok"


class Books:
    """Running books the generator keeps while it writes records."""

    def __init__(self):
        self.Bal = {}
        self.Consumed = {}  # key -> payload of the record that used it
        self.PurchaseOf = {}  # purchase key -> [player, amount, refunded]
        self.Trades = {}  # trade_id -> pending leg dict, or "closed"
        self.Strikes = {}
        self.Severe = set()
        self.Named = set()

    def bal(self, Player):
        return self.Bal.get(Player, 0)

    def strike(self, Player, Severe=False):
        if Severe:
            self.Severe.add(Player)
        self.Strikes[Player] = self.Strikes.get(Player, 0) + 1

    def apply(self, Rec):
        self.Named.add(Rec["player"])
        if "counterparty" in Rec and isinstance(Rec["counterparty"], str):
            self.Named.add(Rec["counterparty"])
        if Rec["type"] == "trade":
            self._trade(Rec)
        else:
            self._keyed(Rec)

    def _keyed(self, Rec):
        Kind = Rec["type"]
        Who = Rec["player"]
        FromPlayer = Kind in PLAYER_TYPES
        if Kind != "refund":
            Grade = _amount_kind(Rec.get("amount"), False)
            if Grade != "ok":
                if FromPlayer:
                    self.strike(Who, Grade == "severe")
                return
        Payload = {K: V for K, V in Rec.items() if K not in ("seq", "attempt")}
        if Rec["key"] in self.Consumed:
            if FromPlayer and self.Consumed[Rec["key"]] != Payload:
                self.strike(Who)
            return
        Amt = Rec.get("amount")
        if Kind == "grant":
            if self.bal(Who) + Amt > CAP:
                return
            self.Bal[Who] = self.bal(Who) + Amt
        elif Kind in ("spend", "purchase"):
            if self.bal(Who) < Amt:
                return
            self.Bal[Who] = self.bal(Who) - Amt
            if Kind == "purchase":
                self.PurchaseOf[Rec["key"]] = [Who, Amt, False]
        else:
            Info = self.PurchaseOf.get(Rec["ref"])
            if Info is None or Info[0] != Who or Info[2]:
                self.strike(Who)
                return
            Info[2] = True
            self.Bal[Who] = self.bal(Who) + Info[1]
        self.Consumed[Rec["key"]] = Payload

    def _trade(self, Rec):
        Who = Rec["player"]
        Grade = _amount_kind(Rec.get("amount"), True)
        if Grade != "ok":
            self.strike(Who, Grade == "severe")
            return
        if Rec["counterparty"] == Who:
            self.strike(Who)
            return
        State = self.Trades.get(Rec["trade_id"])
        if State == "closed":
            return
        if State is None:
            self.Trades[Rec["trade_id"]] = Rec
            return
        if Who == State["player"]:
            return
        if Who != State["counterparty"] or Rec["counterparty"] != State["player"]:
            self.strike(Who)
            return
        self.Trades[Rec["trade_id"]] = "closed"
        A, GiveA = State["player"], State["amount"]
        B, GiveB = Who, Rec["amount"]
        BalA, BalB = self.bal(A), self.bal(B)
        if BalA < GiveA or BalB < GiveB:
            return
        if BalA - GiveA + GiveB > CAP or BalB - GiveB + GiveA > CAP:
            return
        self.Bal[A] = BalA - GiveA + GiveB
        self.Bal[B] = BalB - GiveB + GiveA

    def answer(self):
        Flagged = sorted(
            P for P in self.Named if P in self.Severe or self.Strikes.get(P, 0) >= 3
        )
        return {
            "balances": {P: self.bal(P) for P in sorted(self.Named)},
            "flagged": Flagged,
        }


SEVERE_VALUES = [float("nan"), float("inf"), float("-inf"), -5, -250, -1.5,
                 10**20, MAX_TX + 1, 2.5e9]
MINOR_VALUES = [0, 12.5, 300.0, "100", "abc", True, False, None, [5], {"v": 5}]


class Generator:
    def __init__(self, Seed, Players=24):
        self.R = random.Random(Seed)
        self.Books = Books()
        self.Records = []
        self.Seq = self.R.randint(1000, 5000)
        self.Players = ["pl_%04x" % self.R.randrange(1 << 16) for _ in range(Players)]
        self.Players = sorted(set(self.Players))
        # a few accounts misbehave a lot more than everyone else
        self.Shady = set(self.R.sample(self.Players, max(2, len(self.Players) // 6)))
        self.KeyCount = 0
        self.Struck = set()  # seqs of records that earned a strike
        self.TradeCount = 0
        self.History = []  # keyed records we can replay later
        self.Purchases = []  # purchase keys we have emitted
        self.OpenTrades = []  # first legs that might get answered later
        # normal players only get a small number of slip ups each
        self.Budget = {P: self.R.choice([0, 0, 1, 2, 2, 3, 4, 6]) for P in self.Players}

    def eligible(self, Who):
        return Who in self.Shady or self.Books.Strikes.get(Who, 0) < self.Budget[Who]

    def risky(self, Who):
        # swap in a shady account when this player is out of slip ups
        if self.eligible(Who):
            return Who
        return self.R.choice(sorted(self.Shady))

    def new_key(self):
        self.KeyCount += 1
        return "k%06d%04x" % (self.KeyCount, self.R.randrange(1 << 16))

    def emit(self, Rec):
        self.Seq += self.R.randint(1, 4)
        Rec = dict(Rec)
        Rec["seq"] = self.Seq
        Rec.setdefault("attempt", 1)
        self.Records.append(Rec)
        Before = sum(self.Books.Strikes.values())
        self.Books.apply(Rec)
        if sum(self.Books.Strikes.values()) != Before:
            self.Struck.add(Rec["seq"])
        if Rec["type"] != "trade" and "key" in Rec:
            self.History.append(Rec)
        return Rec

    def who(self):
        if self.R.random() < 0.25:
            return self.R.choice(sorted(self.Shady))
        return self.R.choice(self.Players)

    def good_amount(self, Who, Debit):
        Bal = self.Books.bal(Who)
        R = self.R.random()
        if Debit and Bal > 0 and R < 0.6:
            # sometimes exactly the balance, sometimes one over
            Pick = self.R.choice([Bal, Bal + 1, max(1, Bal // 2), self.R.randint(1, Bal)])
            return min(MAX_TX, max(1, Pick))
        if R < 0.1:
            return MAX_TX
        return self.R.randint(1, 50_000)

    def bad_amount(self, Who):
        if Who in self.Shady and self.R.random() < 0.5:
            return self.R.choice(SEVERE_VALUES)
        if self.R.random() < 0.3:
            return self.R.choice(SEVERE_VALUES)
        return self.R.choice(MINOR_VALUES)

    def step(self):
        R = self.R.random()
        Who = self.who()
        if R < 0.20:
            # server grant, sometimes huge so the cap matters
            Amt = MAX_TX if self.R.random() < 0.3 else self.R.randint(1, 80_000)
            if self.R.random() < 0.05:
                Amt = self.bad_amount(Who)
            self.emit({"type": "grant", "key": self.new_key(), "player": Who, "amount": Amt})
        elif R < 0.32:
            self.emit({"type": "spend", "key": self.new_key(), "player": Who,
                       "amount": self.good_amount(Who, True)})
        elif R < 0.44:
            Rec = self.emit({"type": "purchase", "key": self.new_key(), "player": Who,
                             "amount": self.good_amount(Who, True)})
            self.Purchases.append(Rec)
        elif R < 0.52 and self.Purchases:
            self.refund(Who)
        elif R < 0.64 and self.History:
            self.retry()
        elif R < 0.69 and self.History:
            self.altered_replay()
        elif R < 0.75:
            Kind = self.R.choice(["spend", "purchase", "refund"])
            Who = self.risky(Who)
            Rec = {"type": Kind, "key": self.new_key(), "player": Who}
            if Kind == "refund":
                Rec["ref"] = "k%06d%04x" % (self.R.randrange(1, 10**6), 0)
            elif self.R.random() < 0.1:
                pass  # amount missing on purpose
            else:
                Rec["amount"] = self.bad_amount(Who)
            self.emit(Rec)
        else:
            self.trade_step(Who)

    def whale(self):
        # buy something, get granted right up to the cap, then refund it
        Who = self.R.choice(self.Players)
        if self.Books.bal(Who) < 2:
            self.emit({"type": "grant", "key": self.new_key(), "player": Who,
                       "amount": self.R.randint(10_000, 90_000)})
        Amt = self.R.randint(1, min(MAX_TX, self.Books.bal(Who)))
        Buy = self.emit({"type": "purchase", "key": self.new_key(), "player": Who, "amount": Amt})
        self.Purchases.append(Buy)
        for _ in range(12):
            Room = CAP - self.Books.bal(Who)
            if Room <= 0:
                break
            Give = min(MAX_TX, Room) if self.R.random() < 0.7 else MAX_TX
            self.emit({"type": "grant", "key": self.new_key(), "player": Who, "amount": Give})
        self.emit({"type": "refund", "key": self.new_key(), "player": Who, "ref": Buy["key"]})

    def refund(self, Who):
        Target = self.R.choice(self.Purchases[-40:])
        R = self.R.random()
        Owner = Target["player"]
        if R < 0.7:
            Who = Owner
        if not self.eligible(Who):
            # only let a careful player refund something that will work
            Info = self.Books.PurchaseOf.get(Target["key"])
            if Info is None or Info[0] != Who or Info[2]:
                return
        self.emit({"type": "refund", "key": self.new_key(), "player": Who, "ref": Target["key"]})

    def pick_old(self):
        Pool = [H for H in self.History[-60:] if self.eligible(H["player"])]
        return self.R.choice(Pool) if Pool else None

    def retry(self):
        Old = self.pick_old()
        if Old is None:
            return
        New = {K: V for K, V in Old.items() if K != "seq"}
        New["attempt"] = Old["attempt"] + 1
        self.emit(New)

    def altered_replay(self):
        Old = self.pick_old()
        if Old is None:
            return
        if Old["type"] in ("grant", "refund"):
            return self.retry()
        New = {K: V for K, V in Old.items() if K != "seq"}
        New["attempt"] = Old["attempt"] + 1
        Base = New.get("amount")
        if isinstance(Base, int) and not isinstance(Base, bool):
            New["amount"] = Base + self.R.randint(1, 900)
        else:
            New["amount"] = self.R.randint(1, 900)
        self.emit(New)

    def trade_step(self, Who):
        R = self.R.random()
        if self.OpenTrades and R < 0.55:
            Leg = self.R.choice(self.OpenTrades)
            Q = self.R.random()
            if Q < 0.6:
                # proper answer from the counterparty
                Back = {"type": "trade", "trade_id": Leg["trade_id"],
                        "player": Leg["counterparty"], "counterparty": Leg["player"],
                        "amount": self.trade_amount(Leg["counterparty"])}
                if self.R.random() < 0.06 and self.eligible(Back["player"]):
                    Back["amount"] = self.bad_amount(Back["player"])
                self.emit(Back)
                if self.R.random() < 0.5:
                    self.OpenTrades.remove(Leg)
            elif Q < 0.75:
                # first player retries their own leg, maybe with a new amount
                Again = {K: V for K, V in Leg.items() if K != "seq"}
                Again["attempt"] = Leg["attempt"] + 1
                if self.R.random() < 0.3:
                    Again["amount"] = self.trade_amount(Leg["player"])
                self.emit(Again)
            elif Q < 0.9:
                # somebody else tries to butt in
                Other = self.risky(self.R.choice([P for P in self.Players if P != Leg["player"]]))
                if Other == Leg["player"]:
                    return
                Target = Leg["player"] if self.R.random() < 0.5 else self.R.choice(self.Players)
                if Target == Other:
                    Target = Leg["player"]
                self.emit({"type": "trade", "trade_id": Leg["trade_id"], "player": Other,
                           "counterparty": Target, "amount": self.trade_amount(Other)})
            elif self.eligible(Leg["counterparty"]):
                # right player, wrong counterparty
                Wrong = self.R.choice([P for P in self.Players
                                       if P not in (Leg["player"], Leg["counterparty"])])
                self.emit({"type": "trade", "trade_id": Leg["trade_id"],
                           "player": Leg["counterparty"], "counterparty": Wrong,
                           "amount": self.trade_amount(Leg["counterparty"])})
            return
        self.TradeCount += 1
        Tid = "t%05d%03x" % (self.TradeCount, self.R.randrange(1 << 12))
        Other = self.R.choice([P for P in self.Players if P != Who])
        if self.R.random() < 0.05 and self.eligible(Who):
            Other = Who
        Leg = {"type": "trade", "trade_id": Tid, "player": Who, "counterparty": Other,
               "amount": self.trade_amount(Who)}
        if self.R.random() < 0.06 and self.eligible(Who):
            Leg["amount"] = self.bad_amount(Who)
        Leg = self.emit(Leg)
        self.OpenTrades.append(Leg)
        if len(self.OpenTrades) > 30:
            self.OpenTrades.pop(0)

    def trade_amount(self, Who):
        Bal = self.Books.bal(Who)
        R = self.R.random()
        if R < 0.12:
            return 0
        if R < 0.25:
            return MAX_TX
        if Bal > 0 and R < 0.8:
            return min(MAX_TX, self.R.choice([Bal, Bal + 1, self.R.randint(1, Bal)]))
        return self.R.randint(1, 30_000)

    def build(self, Steps):
        # warm everyone up with a grant so balances are not all zero
        for P in self.Players:
            if self.R.random() < 0.8:
                self.emit({"type": "grant", "key": self.new_key(), "player": P,
                           "amount": self.R.randint(1_000, 400_000)})
        Whales = sorted(self.R.sample(range(Steps), max(1, Steps // 2500)))
        for I in range(Steps):
            self.step()
            while Whales and Whales[0] == I:
                Whales.pop(0)
                self.whale()
        return self.Records


def to_lines(Records, R, Struck=()):
    """Turn records into file lines, out of order, with some copied lines."""
    Lines = []
    for Rec in Records:
        Keys = list(Rec.keys())
        R.shuffle(Keys)
        Text = json.dumps({K: Rec[K] for K in Keys})
        Lines.append((Rec["seq"], Text))
        if R.random() < (0.3 if Rec["seq"] in Struck else 0.03):
            Lines.append((Rec["seq"], Text))
    # arrival order is roughly seq order with a lot of jitter
    Keyed = [(Seq + R.uniform(-60, 60), I, Text) for I, (Seq, Text) in enumerate(Lines)]
    Keyed.sort()
    return [T for _, _, T in Keyed]


def make_case(Seed, Steps, Players=24):
    Gen = Generator(Seed, Players)
    Records = Gen.build(Steps)
    Lines = to_lines(Records, random.Random(Seed * 7919 + 1), Gen.Struck)
    return "\n".join(Lines) + "\n", Gen.Books.answer()
