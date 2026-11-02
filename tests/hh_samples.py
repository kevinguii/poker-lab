"""Hand-written PokerStars-format histories used in tests (invented players and hands).

HAND_A is built to line up with the tree in tests/trees.py: flop Qs Jh 2h, pot 5.0bb,
20bb behind on the flop, OOP (villain) bets 2.5bb = 50% pot, hero (IP) holds AhAd and calls,
then the turn is the 3c and villain checks.
"""

# Cash, $0.50/$1.00. 'Hero' on the button holds AhAd. Both start with $22.50, put $2.50 in preflop
# (pot 5.0bb) and have 20bb behind on the flop.
HAND_A = """PokerStars Hand #900000001:  Hold'em No Limit ($0.50/$1.00 USD) - 2026/10/20 21:14:05 ET
Table 'Testa' 2-max Seat #1 is the button
Seat 1: Hero ($22.50 in chips)
Seat 2: Vil ($22.50 in chips)
Hero: posts small blind $0.50
Vil: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [Ah Ad]
Hero: raises $1.50 to $2.50
Vil: calls $1.50
*** FLOP *** [Qs Jh 2h]
Vil: bets $2.50
Hero: calls $2.50
*** TURN *** [Qs Jh 2h] [3c]
Vil: checks
Hero: bets $5
Vil: folds
Uncalled bet ($5) returned to Hero
Hero collected $10 from pot
*** SUMMARY ***
Total pot $10 | Rake $0
"""

# 6-max, three players see a flop: not heads-up, so not analysable.
HAND_MULTIWAY = """PokerStars Hand #900000002:  Hold'em No Limit ($0.50/$1.00 USD) - 2026/10/20 21:20:11 ET
Table 'Testb' 6-max Seat #3 is the button
Seat 1: Alice ($100 in chips)
Seat 2: Hero ($100 in chips)
Seat 3: Bob ($100 in chips)
Seat 4: Carol ($100 in chips)
Carol: posts small blind $0.50
Alice: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [Qs Jd]
Hero: raises $2 to $3
Bob: calls $3
Carol: folds
Alice: calls $2
*** FLOP *** [Ah 7d 2c]
Alice: checks
Hero: checks
Bob: checks
*** TURN *** [Ah 7d 2c] [Kd]
Alice: checks
Hero: checks
Bob: bets $4
Alice: folds
Hero: folds
*** SUMMARY ***
"""

# 3-bet pot heads up: only analysable if the user has a 3bp preset.
HAND_3BET = """PokerStars Hand #900000003:  Hold'em No Limit ($0.50/$1.00 USD) - 2026/10/20 21:30:00 ET
Table 'Testc' 6-max Seat #1 is the button
Seat 1: Bob ($100 in chips)
Seat 2: Hero ($100 in chips)
Seat 3: Carol ($100 in chips)
Hero: posts small blind $0.50
Carol: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [Kh Kd]
Bob: raises $2 to $3
Hero: raises $10 to $13
Carol: folds
Bob: calls $10
*** FLOP *** [Qs Jh 2h]
Hero: bets $9
Bob: folds
*** SUMMARY ***
"""

# Preflop only: never sees a flop.
HAND_PREFLOP_ONLY = """PokerStars Hand #900000004:  Hold'em No Limit ($0.50/$1.00 USD) - 2026/10/20 21:31:00 ET
Table 'Testd' 2-max Seat #1 is the button
Seat 1: Hero ($100 in chips)
Seat 2: Vil ($100 in chips)
Hero: posts small blind $0.50
Vil: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [7c 2d]
Hero: folds
Uncalled bet ($0.50) returned to Vil
Vil collected $1 from pot
*** SUMMARY ***
"""

# A hero line deliberately unlike the tree: Hero (IP) raises the flop bet to 8.5bb.
HAND_B = HAND_A.replace("#900000001", "#900000005").replace(
    "Hero: calls $2.50\n*** TURN *** [Qs Jh 2h] [3c]\nVil: checks\nHero: bets $5\nVil: folds\nUncalled bet ($5) returned to Hero\nHero collected $10 from pot",
    "Hero: raises $6 to $8.50\nVil: folds\nUncalled bet ($6) returned to Hero\nHero collected $10 from pot",
)
