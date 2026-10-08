"""Reference ledger audit. Usage: python3 audit.py <events.jsonl> <out.json>"""

import json
import math
import sys
from collections import defaultdict

MAX_TX = 1000000
CAP = 10000000
FROM_PLAYERS = ("spend", "purchase", "refund", "trade")


def grade(Amount, AllowZero):
    # returns None when the amount is fine, else "severe" or "minor"
    IsNumber = isinstance(Amount, (int, float)) and not isinstance(Amount, bool)
    if not IsNumber:
        return "minor"
    if Amount != Amount or math.isinf(Amount) or Amount < 0 or Amount > MAX_TX:
        return "severe"
    if isinstance(Amount, float):
        return "minor"
    if Amount == 0 and not AllowZero:
        return "minor"
    return None


class Ledger:
    def __init__(self):
        self.Balance = defaultdict(int)
        self.Seen = set()
        self.KeyOwner = {}
        self.Purchases = {}
        self.Refunded = set()
        self.TradePending = {}
        self.TradeClosed = set()
        self.StrikeCount = defaultdict(int)
        self.HasSevere = set()

    def give_strike(self, Rec, Level="minor"):
        if Rec["type"] not in FROM_PLAYERS:
            return
        self.StrikeCount[Rec["player"]] += 1
        if Level == "severe":
            self.HasSevere.add(Rec["player"])

    def run(self, Rec):
        self.Seen.add(Rec["player"])
        if isinstance(Rec.get("counterparty"), str):
            self.Seen.add(Rec["counterparty"])
        if Rec["type"] == "trade":
            self.on_trade(Rec)
        else:
            self.on_keyed(Rec)

    def on_keyed(self, Rec):
        Type, Player = Rec["type"], Rec["player"]
        if Type != "refund":
            Bad = grade(Rec.get("amount"), False)
            if Bad:
                self.give_strike(Rec, Bad)
                return
        Body = dict(Rec)
        Body.pop("seq", None)
        Body.pop("attempt", None)
        Key = Rec["key"]
        if Key in self.KeyOwner:
            if self.KeyOwner[Key] != Body:
                self.give_strike(Rec)
            return

        if Type == "grant":
            if self.Balance[Player] + Rec["amount"] > CAP:
                return
            self.Balance[Player] += Rec["amount"]
        elif Type == "spend" or Type == "purchase":
            if self.Balance[Player] < Rec["amount"]:
                return
            self.Balance[Player] -= Rec["amount"]
            if Type == "purchase":
                self.Purchases[Key] = (Player, Rec["amount"])
        elif Type == "refund":
            Ref = Rec.get("ref")
            Found = self.Purchases.get(Ref)
            if Found is None or Found[0] != Player or Ref in self.Refunded:
                self.give_strike(Rec)
                return
            self.Refunded.add(Ref)
            self.Balance[Player] += Found[1]
        else:
            return
        self.KeyOwner[Key] = Body

    def on_trade(self, Rec):
        Bad = grade(Rec.get("amount"), True)
        if Bad:
            self.give_strike(Rec, Bad)
            return
        if Rec["counterparty"] == Rec["player"]:
            self.give_strike(Rec)
            return
        Tid = Rec["trade_id"]
        if Tid in self.TradeClosed:
            return
        First = self.TradePending.get(Tid)
        if First is None:
            self.TradePending[Tid] = Rec
            return
        if Rec["player"] == First["player"]:
            return
        if not (Rec["player"] == First["counterparty"] and Rec["counterparty"] == First["player"]):
            self.give_strike(Rec)
            return
        self.TradeClosed.add(Tid)
        del self.TradePending[Tid]
        A, B = First["player"], Rec["player"]
        OutA, OutB = First["amount"], Rec["amount"]
        if self.Balance[A] < OutA or self.Balance[B] < OutB:
            return
        NewA = self.Balance[A] - OutA + OutB
        NewB = self.Balance[B] - OutB + OutA
        if NewA > CAP or NewB > CAP:
            return
        self.Balance[A], self.Balance[B] = NewA, NewB


def main():
    InPath, OutPath = sys.argv[1], sys.argv[2]
    BySeq = {}
    with open(InPath, encoding="utf-8") as Handle:
        for Line in Handle:
            Line = Line.strip()
            if not Line:
                continue
            Rec = json.loads(Line)
            BySeq.setdefault(Rec["seq"], Rec)
    Book = Ledger()
    for Seq in sorted(BySeq):
        Book.run(BySeq[Seq])
    Names = sorted(Book.Seen)
    Result = {
        "balances": {N: Book.Balance[N] for N in Names},
        "flagged": [N for N in Names if N in Book.HasSevere or Book.StrikeCount[N] >= 3],
    }
    with open(OutPath, "w", encoding="utf-8") as Handle:
        json.dump(Result, Handle, indent=2, sort_keys=True)
        Handle.write("\n")


if __name__ == "__main__":
    main()
