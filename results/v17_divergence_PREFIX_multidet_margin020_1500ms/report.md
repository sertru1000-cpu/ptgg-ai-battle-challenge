# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 120 | V17 losses: 64 | V17 wins: 56
Decisions where a real search ran: 4155
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 367 (8.8% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 56/367 (15.3%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 1078/3788 (28.5%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 57 | In games V17 lost: 32 | Win rate when this diverged: 43.9%
- Of these, backed by a rollout that hit a terminal reward: 13/57 (22.8%)
  - game 0 decision 60 (turn 9, visits=314, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 0 decision 70 (turn 11, visits=308, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played Night Stretcher (attackId=None)
  - game 1 decision 5 (turn 1, visits=372, hit_terminal=False): MCTS played Dreepy (attackId=None) | V6 would have played Dreepy (attackId=None)

### MCTS:[ATTACH] vs V6:[PLAY]
- Occurrences: 51 | In games V17 lost: 22 | Win rate when this diverged: 56.9%
- Of these, backed by a rollout that hit a terminal reward: 5/51 (9.8%)
  - game 0 decision 5 (turn 1, visits=428, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Meowth ex (attackId=None)
  - game 11 decision 9 (turn 3, visits=358, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Crispin (attackId=None)
  - game 18 decision 17 (turn 5, visits=304, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Crispin (attackId=None)

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 37 | In games V17 lost: 21 | Win rate when this diverged: 43.2%
- Of these, backed by a rollout that hit a terminal reward: 8/37 (21.6%)
  - game 0 decision 52 (turn 7, visits=305, hit_terminal=False): MCTS played Brock’s Scouting (attackId=None) | V6 would have played None (attackId=None)
  - game 3 decision 39 (turn 9, visits=302, hit_terminal=False): MCTS played Brock’s Scouting (attackId=None) | V6 would have played None (attackId=None)
  - game 5 decision 70 (turn 11, visits=278, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 36 | In games V17 lost: 21 | Win rate when this diverged: 41.7%
- Of these, backed by a rollout that hit a terminal reward: 9/36 (25.0%)
  - game 0 decision 59 (turn 7, visits=298, hit_terminal=False): MCTS played None (attackId=153) | V6 would have played Crushing Hammer (attackId=None)
  - game 0 decision 97 (turn 13, visits=283, hit_terminal=True): MCTS played None (attackId=154) | V6 would have played Boss’s Orders (attackId=None)
  - game 0 decision 104 (turn 15, visits=326, hit_terminal=True): MCTS played None (attackId=153) | V6 would have played Crushing Hammer (attackId=None)

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 31 | In games V17 lost: 18 | Win rate when this diverged: 41.9%
- Of these, backed by a rollout that hit a terminal reward: 8/31 (25.8%)
  - game 4 decision 37 (turn 7, visits=286, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)
  - game 19 decision 77 (turn 13, visits=284, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)
  - game 21 decision 25 (turn 7, visits=329, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)

### MCTS:[ATTACH] vs V6:[ABILITY]
- Occurrences: 27 | In games V17 lost: 11 | Win rate when this diverged: 59.3%
- Of these, backed by a rollout that hit a terminal reward: 1/27 (3.7%)
  - game 3 decision 18 (turn 3, visits=357, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 3 decision 42 (turn 9, visits=304, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 3 decision 59 (turn 11, visits=287, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[ATTACK] vs V6:[ABILITY]
- Occurrences: 17 | In games V17 lost: 12 | Win rate when this diverged: 29.4%
- Of these, backed by a rollout that hit a terminal reward: 2/17 (11.8%)
  - game 3 decision 26 (turn 5, visits=339, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played None (attackId=None)
  - game 6 decision 13 (turn 3, visits=356, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played None (attackId=None)
  - game 19 decision 8 (turn 3, visits=363, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played None (attackId=None)

### MCTS:[ATTACH] vs V6:[EVOLVE]
- Occurrences: 13 | In games V17 lost: 8 | Win rate when this diverged: 38.5%
- Of these, backed by a rollout that hit a terminal reward: 1/13 (7.7%)
  - game 0 decision 55 (turn 7, visits=317, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 3 decision 24 (turn 5, visits=339, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 4 decision 10 (turn 3, visits=339, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 12 | In games V17 lost: 10 | Win rate when this diverged: 16.7%
- Of these, backed by a rollout that hit a terminal reward: 0/12 (0.0%)
  - game 5 decision 45 (turn 7, visits=294, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 18 decision 23 (turn 7, visits=312, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Crispin (attackId=None)
  - game 21 decision 21 (turn 7, visits=340, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Dreepy (attackId=None)

### MCTS:[RETREAT] vs V6:[PLAY]
- Occurrences: 11 | In games V17 lost: 8 | Win rate when this diverged: 27.3%
- Of these, backed by a rollout that hit a terminal reward: 1/11 (9.1%)
  - game 0 decision 16 (turn 3, visits=360, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Buddy-Buddy Poffin (attackId=None)
  - game 3 decision 14 (turn 3, visits=367, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Lillie's Determination (attackId=None)
  - game 3 decision 53 (turn 9, visits=302, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Poké Pad (attackId=None)

### MCTS:[ABILITY] vs V6:[PLAY]
- Occurrences: 9 | In games V17 lost: 4 | Win rate when this diverged: 55.6%
- Of these, backed by a rollout that hit a terminal reward: 2/9 (22.2%)
  - game 21 decision 32 (turn 9, visits=308, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 51 decision 24 (turn 7, visits=286, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Buddy-Buddy Poffin (attackId=None)
  - game 68 decision 23 (turn 6, visits=306, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Poké Pad (attackId=None)

### MCTS:[ABILITY] vs V6:[EVOLVE]
- Occurrences: 8 | In games V17 lost: 7 | Win rate when this diverged: 12.5%
- Of these, backed by a rollout that hit a terminal reward: 2/8 (25.0%)
  - game 0 decision 54 (turn 7, visits=309, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 5 decision 17 (turn 5, visits=527, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 5 decision 19 (turn 5, visits=500, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)

### MCTS:[EVOLVE] vs V6:[EVOLVE]
- Occurrences: 8 | In games V17 lost: 7 | Win rate when this diverged: 12.5%
- Of these, backed by a rollout that hit a terminal reward: 0/8 (0.0%)
  - game 4 decision 20 (turn 5, visits=299, hit_terminal=False): MCTS played Dragapult ex (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 22 decision 12 (turn 3, visits=386, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 68 decision 26 (turn 6, visits=298, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Drakloak (attackId=None)

### MCTS:[END] vs V6:[ATTACK]
- Occurrences: 7 | In games V17 lost: 4 | Win rate when this diverged: 42.9%
- Of these, backed by a rollout that hit a terminal reward: 3/7 (42.9%)
  - game 3 decision 33 (turn 7, visits=326, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played None (attackId=323)
  - game 45 decision 9 (turn 3, visits=419, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=243)
  - game 111 decision 15 (turn 2, visits=362, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played None (attackId=323)

### MCTS:[ATTACK] vs V6:[EVOLVE]
- Occurrences: 6 | In games V17 lost: 3 | Win rate when this diverged: 50.0%
- Of these, backed by a rollout that hit a terminal reward: 0/6 (0.0%)
  - game 4 decision 56 (turn 9, visits=290, hit_terminal=False): MCTS played None (attackId=153) | V6 would have played Drakloak (attackId=None)
  - game 111 decision 18 (turn 4, visits=343, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Drakloak (attackId=None)
  - game 114 decision 23 (turn 8, visits=359, hit_terminal=False): MCTS played None (attackId=152) | V6 would have played Dragapult ex (attackId=None)

## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)

### Cards played in games V17 LOST

- Crispin: 2
- Crushing Hammer: 1
- Lillie's Determination: 1
- Budew: 1

### Cards played in games V17 WON

- Brock’s Scouting: 1

## Raw Data

- Per-decision: `results\v17_divergence\raw_decisions.jsonl`
- Per-game: `results\v17_divergence\raw_games.jsonl`