# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 120 | V17 losses: 63 | V17 wins: 57
Decisions where a real search ran: 4089
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 578 (14.1% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 87/578 (15.1%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 1040/3511 (29.6%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 102 | In games V17 lost: 57 | Win rate when this diverged: 44.1%
- Of these, backed by a rollout that hit a terminal reward: 16/102 (15.7%)
  - game 1 decision 4 (turn 1, visits=218, hit_terminal=False): MCTS played Team Rocket's Watchtower (attackId=None) | V6 would have played Team Rocket's Watchtower (attackId=None)
  - game 1 decision 41 (turn 11, visits=138, hit_terminal=False): MCTS played Brock’s Scouting (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 2 decision 32 (turn 11, visits=158, hit_terminal=False): MCTS played Ultra Ball (attackId=None) | V6 would have played Buddy-Buddy Poffin (attackId=None)

### MCTS:[ATTACH] vs V6:[PLAY]
- Occurrences: 88 | In games V17 lost: 51 | Win rate when this diverged: 42.0%
- Of these, backed by a rollout that hit a terminal reward: 10/88 (11.4%)
  - game 1 decision 27 (turn 11, visits=143, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Buddy-Buddy Poffin (attackId=None)
  - game 2 decision 5 (turn 3, visits=198, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Meowth ex (attackId=None)
  - game 3 decision 28 (turn 5, visits=151, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Crispin (attackId=None)

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 48 | In games V17 lost: 31 | Win rate when this diverged: 35.4%
- Of these, backed by a rollout that hit a terminal reward: 9/48 (18.8%)
  - game 1 decision 35 (turn 11, visits=131, hit_terminal=False): MCTS played Unfair Stamp (attackId=None) | V6 would have played None (attackId=None)
  - game 3 decision 11 (turn 3, visits=164, hit_terminal=False): MCTS played Lillie's Determination (attackId=None) | V6 would have played None (attackId=None)
  - game 3 decision 71 (turn 11, visits=142, hit_terminal=False): MCTS played Unfair Stamp (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 46 | In games V17 lost: 20 | Win rate when this diverged: 56.5%
- Of these, backed by a rollout that hit a terminal reward: 18/46 (39.1%)
  - game 1 decision 43 (turn 11, visits=145, hit_terminal=False): MCTS played None (attackId=152) | V6 would have played Crushing Hammer (attackId=None)
  - game 2 decision 9 (turn 3, visits=196, hit_terminal=False): MCTS played None (attackId=151) | V6 would have played Lillie's Determination (attackId=None)
  - game 2 decision 13 (turn 5, visits=185, hit_terminal=False): MCTS played None (attackId=150) | V6 would have played Dreepy (attackId=None)

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 40 | In games V17 lost: 20 | Win rate when this diverged: 50.0%
- Of these, backed by a rollout that hit a terminal reward: 6/40 (15.0%)
  - game 1 decision 14 (turn 5, visits=170, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Basic {R} Energy (attackId=None)
  - game 3 decision 12 (turn 3, visits=160, hit_terminal=False): MCTS played Lucky Helmet (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 10 decision 13 (turn 3, visits=175, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 32 | In games V17 lost: 20 | Win rate when this diverged: 37.5%
- Of these, backed by a rollout that hit a terminal reward: 0/32 (0.0%)
  - game 1 decision 38 (turn 11, visits=146, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 2 decision 42 (turn 11, visits=164, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 12 decision 9 (turn 3, visits=190, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Crispin (attackId=None)

### MCTS:[ATTACK] vs V6:[ABILITY]
- Occurrences: 29 | In games V17 lost: 11 | Win rate when this diverged: 62.1%
- Of these, backed by a rollout that hit a terminal reward: 3/29 (10.3%)
  - game 12 decision 39 (turn 9, visits=164, hit_terminal=False): MCTS played None (attackId=152) | V6 would have played None (attackId=None)
  - game 12 decision 71 (turn 13, visits=137, hit_terminal=False): MCTS played None (attackId=153) | V6 would have played None (attackId=None)
  - game 19 decision 46 (turn 9, visits=150, hit_terminal=False): MCTS played None (attackId=154) | V6 would have played None (attackId=None)

### MCTS:[ATTACH] vs V6:[ABILITY]
- Occurrences: 26 | In games V17 lost: 13 | Win rate when this diverged: 50.0%
- Of these, backed by a rollout that hit a terminal reward: 3/26 (11.5%)
  - game 3 decision 13 (turn 3, visits=164, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 12 decision 14 (turn 3, visits=194, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 38 decision 23 (turn 5, visits=178, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[ATTACH] vs V6:[EVOLVE]
- Occurrences: 19 | In games V17 lost: 14 | Win rate when this diverged: 26.3%
- Of these, backed by a rollout that hit a terminal reward: 3/19 (15.8%)
  - game 7 decision 11 (turn 3, visits=184, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 14 decision 18 (turn 3, visits=167, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 22 decision 14 (turn 3, visits=196, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)

### MCTS:[ATTACK] vs V6:[ATTACH]
- Occurrences: 17 | In games V17 lost: 12 | Win rate when this diverged: 29.4%
- Of these, backed by a rollout that hit a terminal reward: 3/17 (17.6%)
  - game 2 decision 29 (turn 9, visits=172, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Basic {R} Energy (attackId=None)
  - game 19 decision 20 (turn 3, visits=179, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Basic {R} Energy (attackId=None)
  - game 19 decision 45 (turn 7, visits=150, hit_terminal=False): MCTS played None (attackId=153) | V6 would have played Basic {R} Energy (attackId=None)

### MCTS:[ABILITY] vs V6:[EVOLVE]
- Occurrences: 17 | In games V17 lost: 6 | Win rate when this diverged: 64.7%
- Of these, backed by a rollout that hit a terminal reward: 1/17 (5.9%)
  - game 20 decision 11 (turn 5, visits=163, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 22 decision 26 (turn 7, visits=176, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 34 decision 18 (turn 9, visits=175, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)

### MCTS:[ABILITY] vs V6:[PLAY]
- Occurrences: 15 | In games V17 lost: 10 | Win rate when this diverged: 33.3%
- Of these, backed by a rollout that hit a terminal reward: 5/15 (33.3%)
  - game 1 decision 39 (turn 11, visits=146, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Crushing Hammer (attackId=None)
  - game 3 decision 72 (turn 11, visits=145, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Poké Pad (attackId=None)
  - game 12 decision 49 (turn 11, visits=150, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)

### MCTS:[EVOLVE] vs V6:[EVOLVE]
- Occurrences: 15 | In games V17 lost: 9 | Win rate when this diverged: 40.0%
- Of these, backed by a rollout that hit a terminal reward: 1/15 (6.7%)
  - game 1 decision 34 (turn 11, visits=138, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 3 decision 10 (turn 3, visits=158, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 28 decision 13 (turn 3, visits=170, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Drakloak (attackId=None)

### MCTS:[ATTACK] vs V6:[EVOLVE]
- Occurrences: 15 | In games V17 lost: 9 | Win rate when this diverged: 40.0%
- Of these, backed by a rollout that hit a terminal reward: 1/15 (6.7%)
  - game 14 decision 19 (turn 3, visits=166, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Drakloak (attackId=None)
  - game 16 decision 18 (turn 7, visits=168, hit_terminal=False): MCTS played None (attackId=150) | V6 would have played Drakloak (attackId=None)
  - game 22 decision 15 (turn 3, visits=175, hit_terminal=False): MCTS played None (attackId=323) | V6 would have played Drakloak (attackId=None)

### MCTS:[RETREAT] vs V6:[PLAY]
- Occurrences: 14 | In games V17 lost: 9 | Win rate when this diverged: 35.7%
- Of these, backed by a rollout that hit a terminal reward: 1/14 (7.1%)
  - game 2 decision 14 (turn 7, visits=183, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 28 decision 37 (turn 9, visits=141, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dreepy (attackId=None)
  - game 59 decision 28 (turn 5, visits=172, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Crushing Hammer (attackId=None)

## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)

### Cards played in games V17 LOST

- Crispin: 2
- Night Stretcher: 1
- Budew: 1
- Lillie's Determination: 1

### Cards played in games V17 WON

- Lillie's Determination: 1

## Raw Data

- Per-decision: `results\v17_divergence\raw_decisions.jsonl`
- Per-game: `results\v17_divergence\raw_games.jsonl`