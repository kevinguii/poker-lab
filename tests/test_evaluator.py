import pytest

from pokerlab.evaluator import best_hand, describe, rank5, showdown

ORDER = [  # weakest to strongest, one representative each
    "As Kd 9c 5h 3d".split(),         # high card
    "As Ad 9c 5h 3d".split(),         # pair
    "As Ad 9c 9h 3d".split(),         # two pair
    "As Ad Ac 5h 3d".split(),         # trips
    "5s 6d 7c 8h 9d".split(),         # straight
    "As 2s 9s 5s 3s".split(),         # flush
    "As Ad Ac 5h 5d".split(),         # full house
    "As Ad Ac Ah 3d".split(),         # quads
    "5s 6s 7s 8s 9s".split(),         # straight flush
]


def test_category_order():
    ranks = [rank5(h) for h in ORDER]
    assert ranks == sorted(ranks)
    assert [r[0] for r in ranks] == list(range(9))


def test_wheel_is_the_lowest_straight():
    wheel, six_high = rank5("As 2d 3c 4h 5d".split()), rank5("2s 3d 4c 5h 6d".split())
    assert wheel[0] == six_high[0] == 4 and wheel < six_high


def test_kickers_break_ties():
    assert rank5("As Ad Kc 5h 3d".split()) > rank5("As Ad Qc 5h 3d".split())
    assert rank5("Ks Kd Ac 5h 3d".split()) < rank5("As Ad 2c 5h 3d".split())  # pair rank first


def test_best_of_seven_picks_the_straight_over_the_pair():
    r = best_hand("5s 6d 7c 8h 9d As Ad".split())
    assert r[0] == 4 and describe(r) == "Straight, Nine high"


def test_flush_beats_straight_on_same_board():
    board = "2s 7s 9s Kd 4h".split()
    assert showdown(["As", "3s"], ["8h", "Td"], board) == 1   # nut-ish flush vs nothing
    # hero has 4-8 straight; villain has six spades
    assert showdown(["6d", "5c"], ["As", "3s"], "3d 4s 7s 8s 2s".split()) == -1


def test_split_pot_when_board_plays():
    board = "As Ks Qs Js Ts".split()  # royal flush on board
    assert showdown(["2c", "3c"], ["4d", "5d"], board) == 0


@pytest.mark.parametrize(
    "cards,name",
    [
        ("Qs Qd 2c 7h 3d", "Pair of Queens"),
        ("Qs Qd 2c 2h 3d", "Two pair, Queens and Twos"),
        ("6s 6d 6c 2h 3d", "Three of a kind, Sixes"),
        ("As Ad Ac Kh Kd", "Full house, Aces full of Kings"),
        ("As Ks Qs Js Ts", "Royal flush"),
        ("Ah Kd 9c 5h 3d", "Ace high"),
    ],
)
def test_names(cards, name):
    assert describe(rank5(cards.split())) == name


def test_needs_five_to_seven_cards():
    with pytest.raises(ValueError):
        best_hand(["As", "Kd"])


def test_fast_rank_matches_best_hand_ordering():
    import random

    from pokerlab.evaluator import best_hand, fast_rank, pack_rank

    deck = [r + s for r in "AKQJT98765432" for s in "cdhs"]
    rng = random.Random(11)
    for n in (5, 6, 7):
        for _ in range(4000):
            cards = rng.sample(deck, n)
            assert fast_rank(cards) == pack_rank(best_hand(cards)), cards


def test_fast_rank_special_hands():
    from pokerlab.evaluator import fast_rank

    wheel = fast_rank(["Ac", "2d", "3h", "4s", "5c", "Kd", "Kh"])
    six_high = fast_rank(["2c", "3d", "4h", "5s", "6c", "Kd", "Kh"])
    assert wheel < six_high
    assert fast_rank(["Ah", "Kh", "Qh", "Jh", "Th", "2c", "2d"]) > fast_rank(["9s", "9c", "9h", "9d", "Ac", "Ad", "Ah"])
