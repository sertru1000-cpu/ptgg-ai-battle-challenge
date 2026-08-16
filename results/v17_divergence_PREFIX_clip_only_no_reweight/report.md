# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 80 | V17 losses: 66 | V17 wins: 14
Decisions where a real search ran: 2369
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 1124 (47.4% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 841/1124 (74.8%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 1101/1245 (88.4%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 340 | In games V17 lost: 289 | Win rate when this diverged: 15.0%
- Of these, backed by a rollout that hit a terminal reward: 260/340 (76.5%)
  - game 1 decision 4 (turn 3, visits=63, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played Lillie's Determination (attackId=None)
  - game 1 decision 11 (turn 5, visits=59, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 1 decision 18 (turn 7, visits=126, hit_terminal=True): MCTS played Ultra Ball (attackId=None) | V6 would have played Poké Pad (attackId=None)

### MCTS:[ATTACH] vs V6:[PLAY]
- Occurrences: 111 | In games V17 lost: 94 | Win rate when this diverged: 15.3%
- Of these, backed by a rollout that hit a terminal reward: 79/111 (71.2%)
  - game 1 decision 10 (turn 5, visits=66, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Ultra Ball (attackId=None)
  - game 2 decision 2 (turn 1, visits=84, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Team Rocket's Watchtower (attackId=None)
  - game 2 decision 18 (turn 7, visits=50, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Crushing Hammer (attackId=None)

### MCTS:[END] vs V6:[PLAY]
- Occurrences: 91 | In games V17 lost: 80 | Win rate when this diverged: 12.1%
- Of these, backed by a rollout that hit a terminal reward: 67/91 (73.6%)
  - game 2 decision 3 (turn 1, visits=91, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Team Rocket's Watchtower (attackId=None)
  - game 2 decision 30 (turn 9, visits=69, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Lillie's Determination (attackId=None)
  - game 3 decision 3 (turn 3, visits=61, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 71 | In games V17 lost: 61 | Win rate when this diverged: 14.1%
- Of these, backed by a rollout that hit a terminal reward: 52/71 (73.2%)
  - game 2 decision 10 (turn 3, visits=63, hit_terminal=True): MCTS played None (attackId=323) | V6 would have played Meowth ex (attackId=None)
  - game 2 decision 15 (turn 5, visits=40, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Latias ex (attackId=None)
  - game 5 decision 7 (turn 3, visits=65, hit_terminal=True): MCTS played None (attackId=151) | V6 would have played Buddy-Buddy Poffin (attackId=None)

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 57 | In games V17 lost: 43 | Win rate when this diverged: 24.6%
- Of these, backed by a rollout that hit a terminal reward: 46/57 (80.7%)
  - game 4 decision 36 (turn 11, visits=146, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played None (attackId=None)
  - game 5 decision 34 (turn 9, visits=52, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played None (attackId=None)
  - game 7 decision 9 (turn 3, visits=92, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[RETREAT] vs V6:[PLAY]
- Occurrences: 52 | In games V17 lost: 42 | Win rate when this diverged: 19.2%
- Of these, backed by a rollout that hit a terminal reward: 44/52 (84.6%)
  - game 5 decision 17 (turn 7, visits=53, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 6 decision 31 (turn 7, visits=60, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 6 decision 46 (turn 11, visits=65, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Night Stretcher (attackId=None)

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 46 | In games V17 lost: 39 | Win rate when this diverged: 15.2%
- Of these, backed by a rollout that hit a terminal reward: 32/46 (69.6%)
  - game 5 decision 20 (turn 7, visits=53, hit_terminal=True): MCTS played Drakloak (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 6 decision 48 (turn 11, visits=61, hit_terminal=True): MCTS played Drakloak (attackId=None) | V6 would have played Night Stretcher (attackId=None)
  - game 7 decision 8 (turn 3, visits=75, hit_terminal=True): MCTS played Drakloak (attackId=None) | V6 would have played Crispin (attackId=None)

### MCTS:[ABILITY] vs V6:[PLAY]
- Occurrences: 44 | In games V17 lost: 38 | Win rate when this diverged: 13.6%
- Of these, backed by a rollout that hit a terminal reward: 32/44 (72.7%)
  - game 5 decision 21 (turn 7, visits=54, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 6 decision 23 (turn 7, visits=67, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Budew (attackId=None)
  - game 6 decision 43 (turn 11, visits=83, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Night Stretcher (attackId=None)

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 32 | In games V17 lost: 27 | Win rate when this diverged: 15.6%
- Of these, backed by a rollout that hit a terminal reward: 25/32 (78.1%)
  - game 6 decision 8 (turn 5, visits=70, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)
  - game 6 decision 34 (turn 7, visits=61, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)
  - game 9 decision 12 (turn 5, visits=68, hit_terminal=True): MCTS played Lucky Helmet (attackId=None) | V6 would have played Lucky Helmet (attackId=None)

### MCTS:[PLAY] vs V6:[EVOLVE]
- Occurrences: 27 | In games V17 lost: 20 | Win rate when this diverged: 25.9%
- Of these, backed by a rollout that hit a terminal reward: 17/27 (63.0%)
  - game 9 decision 21 (turn 9, visits=61, hit_terminal=False): MCTS played Dreepy (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 10 decision 42 (turn 9, visits=56, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 12 decision 11 (turn 3, visits=66, hit_terminal=False): MCTS played Team Rocket's Watchtower (attackId=None) | V6 would have played Drakloak (attackId=None)

### MCTS:[PLAY] vs V6:[ATTACH]
- Occurrences: 24 | In games V17 lost: 18 | Win rate when this diverged: 25.0%
- Of these, backed by a rollout that hit a terminal reward: 17/24 (70.8%)
  - game 1 decision 13 (turn 5, visits=82, hit_terminal=True): MCTS played Crushing Hammer (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 1 decision 15 (turn 5, visits=83, hit_terminal=True): MCTS played Team Rocket's Watchtower (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 4 decision 19 (turn 7, visits=83, hit_terminal=True): MCTS played Buddy-Buddy Poffin (attackId=None) | V6 would have played Basic {R} Energy (attackId=None)

### MCTS:[ATTACK] vs V6:[ABILITY]
- Occurrences: 24 | In games V17 lost: 15 | Win rate when this diverged: 37.5%
- Of these, backed by a rollout that hit a terminal reward: 18/24 (75.0%)
  - game 5 decision 40 (turn 9, visits=65, hit_terminal=True): MCTS played None (attackId=152) | V6 would have played None (attackId=None)
  - game 15 decision 13 (turn 3, visits=65, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played None (attackId=None)
  - game 17 decision 44 (turn 9, visits=82, hit_terminal=True): MCTS played None (attackId=150) | V6 would have played None (attackId=None)

### MCTS:[ATTACH] vs V6:[ABILITY]
- Occurrences: 20 | In games V17 lost: 14 | Win rate when this diverged: 30.0%
- Of these, backed by a rollout that hit a terminal reward: 12/20 (60.0%)
  - game 5 decision 39 (turn 9, visits=61, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 10 decision 20 (turn 5, visits=64, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 15 decision 12 (turn 3, visits=66, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[END] vs V6:[ABILITY]
- Occurrences: 19 | In games V17 lost: 17 | Win rate when this diverged: 10.5%
- Of these, backed by a rollout that hit a terminal reward: 12/19 (63.2%)
  - game 12 decision 13 (turn 3, visits=64, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played None (attackId=None)
  - game 17 decision 15 (turn 5, visits=80, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=None)
  - game 28 decision 10 (turn 3, visits=69, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[END] vs V6:[ATTACK]
- Occurrences: 18 | In games V17 lost: 15 | Win rate when this diverged: 16.7%
- Of these, backed by a rollout that hit a terminal reward: 13/18 (72.2%)
  - game 4 decision 11 (turn 3, visits=70, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=151)
  - game 6 decision 35 (turn 7, visits=61, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played None (attackId=323)
  - game 30 decision 10 (turn 3, visits=80, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=323)

## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)

### Cards played in games V17 LOST

- Dreepy: 3
- Ultra Ball: 3
- Lillie's Determination: 3
- Team Rocket's Watchtower: 2
- Night Stretcher: 2
- Meowth ex: 2
- Crispin: 1
- Boss’s Orders: 1
- Budew: 1
- Brock’s Scouting: 1
- Latias ex: 1

### Cards played in games V17 WON

- Dreepy: 1
- Meowth ex: 1
- Unfair Stamp: 1
- Night Stretcher: 1
- Buddy-Buddy Poffin: 1
- Boss’s Orders: 1
- Team Rocket's Watchtower: 1

## Raw Data

- Per-decision: `results\v17_divergence\raw_decisions.jsonl`
- Per-game: `results\v17_divergence\raw_games.jsonl`