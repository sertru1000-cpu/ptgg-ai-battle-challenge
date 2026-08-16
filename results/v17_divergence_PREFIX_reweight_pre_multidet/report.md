# V17 MCTS vs V6-Greedy Divergence Analysis

Games: 60 | V17 losses: 48 | V17 wins: 12
Decisions where a real search ran: 1914
Decisions where MCTS's final pick != V6's raw greedy pick ("diverged"): 888 (46.4% of searched decisions)

## Terminal-reward correlation (testing the mean-scaling hypothesis)

- Diverged decisions where at least one backing rollout hit a terminal (+-1,000,000) reward: 647/888 (72.9%)
- Non-diverged decisions where at least one backing rollout hit a terminal reward: 933/1026 (90.9%)

If divergence is disproportionately associated with a terminal-reward hit, that directly supports the hypothesis that a single rare simulated conclusion (not a stable multi-sample signal) is what's flipping MCTS's pick away from the greedy choice.

## Top Divergence Patterns (MCTS override vs V6 greedy)

### MCTS:[PLAY] vs V6:[PLAY]
- Occurrences: 283 | In games V17 lost: 241 | Win rate when this diverged: 14.8%
- Of these, backed by a rollout that hit a terminal reward: 209/283 (73.9%)
  - game 1 decision 5 (turn 3, visits=67, hit_terminal=False): MCTS played Lillie's Determination (attackId=None) | V6 would have played Lillie's Determination (attackId=None)
  - game 1 decision 7 (turn 5, visits=64, hit_terminal=True): MCTS played Dreepy (attackId=None) | V6 would have played Budew (attackId=None)
  - game 1 decision 11 (turn 7, visits=60, hit_terminal=False): MCTS played Dreepy (attackId=None) | V6 would have played Rare Candy (attackId=None)

### MCTS:[ATTACH] vs V6:[PLAY]
- Occurrences: 90 | In games V17 lost: 72 | Win rate when this diverged: 20.0%
- Of these, backed by a rollout that hit a terminal reward: 66/90 (73.3%)
  - game 1 decision 8 (turn 5, visits=64, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Budew (attackId=None)
  - game 1 decision 18 (turn 7, visits=56, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Fezandipiti ex (attackId=None)
  - game 2 decision 5 (turn 3, visits=103, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Dreepy (attackId=None)

### MCTS:[END] vs V6:[PLAY]
- Occurrences: 60 | In games V17 lost: 53 | Win rate when this diverged: 11.7%
- Of these, backed by a rollout that hit a terminal reward: 42/60 (70.0%)
  - game 1 decision 3 (turn 1, visits=94, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Buddy-Buddy Poffin (attackId=None)
  - game 1 decision 6 (turn 3, visits=55, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Budew (attackId=None)
  - game 1 decision 9 (turn 5, visits=69, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Budew (attackId=None)

### MCTS:[ATTACK] vs V6:[PLAY]
- Occurrences: 58 | In games V17 lost: 47 | Win rate when this diverged: 19.0%
- Of these, backed by a rollout that hit a terminal reward: 45/58 (77.6%)
  - game 4 decision 37 (turn 7, visits=64, hit_terminal=True): MCTS played None (attackId=154) | V6 would have played Crushing Hammer (attackId=None)
  - game 5 decision 43 (turn 11, visits=67, hit_terminal=True): MCTS played None (attackId=154) | V6 would have played Rare Candy (attackId=None)
  - game 5 decision 55 (turn 13, visits=90, hit_terminal=True): MCTS played None (attackId=154) | V6 would have played Unfair Stamp (attackId=None)

### MCTS:[ABILITY] vs V6:[PLAY]
- Occurrences: 40 | In games V17 lost: 33 | Win rate when this diverged: 17.5%
- Of these, backed by a rollout that hit a terminal reward: 29/40 (72.5%)
  - game 2 decision 36 (turn 7, visits=87, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Night Stretcher (attackId=None)
  - game 2 decision 41 (turn 7, visits=109, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Night Stretcher (attackId=None)
  - game 4 decision 34 (turn 7, visits=63, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Fezandipiti ex (attackId=None)

### MCTS:[PLAY] vs V6:[ABILITY]
- Occurrences: 38 | In games V17 lost: 29 | Win rate when this diverged: 23.7%
- Of these, backed by a rollout that hit a terminal reward: 29/38 (76.3%)
  - game 1 decision 36 (turn 9, visits=53, hit_terminal=True): MCTS played Brock’s Scouting (attackId=None) | V6 would have played None (attackId=None)
  - game 2 decision 18 (turn 5, visits=68, hit_terminal=True): MCTS played Lillie's Determination (attackId=None) | V6 would have played None (attackId=None)
  - game 8 decision 52 (turn 13, visits=113, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[EVOLVE] vs V6:[PLAY]
- Occurrences: 37 | In games V17 lost: 34 | Win rate when this diverged: 8.1%
- Of these, backed by a rollout that hit a terminal reward: 29/37 (78.4%)
  - game 2 decision 39 (turn 7, visits=84, hit_terminal=True): MCTS played Drakloak (attackId=None) | V6 would have played Night Stretcher (attackId=None)
  - game 4 decision 29 (turn 7, visits=63, hit_terminal=True): MCTS played Drakloak (attackId=None) | V6 would have played Ultra Ball (attackId=None)
  - game 5 decision 19 (turn 7, visits=58, hit_terminal=False): MCTS played Drakloak (attackId=None) | V6 would have played Brock’s Scouting (attackId=None)

### MCTS:[RETREAT] vs V6:[PLAY]
- Occurrences: 30 | In games V17 lost: 24 | Win rate when this diverged: 20.0%
- Of these, backed by a rollout that hit a terminal reward: 26/30 (86.7%)
  - game 1 decision 27 (turn 7, visits=55, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Fezandipiti ex (attackId=None)
  - game 4 decision 16 (turn 5, visits=58, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Lillie's Determination (attackId=None)
  - game 8 decision 41 (turn 11, visits=71, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Lillie's Determination (attackId=None)

### MCTS:[PLAY] vs V6:[ATTACH]
- Occurrences: 29 | In games V17 lost: 24 | Win rate when this diverged: 17.2%
- Of these, backed by a rollout that hit a terminal reward: 18/29 (62.1%)
  - game 4 decision 3 (turn 1, visits=85, hit_terminal=True): MCTS played Buddy-Buddy Poffin (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 5 decision 5 (turn 1, visits=88, hit_terminal=True): MCTS played Ultra Ball (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 5 decision 8 (turn 1, visits=115, hit_terminal=True): MCTS played Night Stretcher (attackId=None) | V6 would have played Lucky Helmet (attackId=None)

### MCTS:[PLAY] vs V6:[EVOLVE]
- Occurrences: 26 | In games V17 lost: 17 | Win rate when this diverged: 34.6%
- Of these, backed by a rollout that hit a terminal reward: 16/26 (61.5%)
  - game 5 decision 22 (turn 9, visits=60, hit_terminal=False): MCTS played Buddy-Buddy Poffin (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 8 decision 5 (turn 5, visits=72, hit_terminal=True): MCTS played Crispin (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 11 decision 17 (turn 9, visits=61, hit_terminal=False): MCTS played Ultra Ball (attackId=None) | V6 would have played Dragapult ex (attackId=None)

### MCTS:[ATTACH] vs V6:[ATTACH]
- Occurrences: 26 | In games V17 lost: 19 | Win rate when this diverged: 26.9%
- Of these, backed by a rollout that hit a terminal reward: 16/26 (61.5%)
  - game 4 decision 2 (turn 1, visits=92, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 4 decision 5 (turn 1, visits=84, hit_terminal=True): MCTS played Lucky Helmet (attackId=None) | V6 would have played Lucky Helmet (attackId=None)
  - game 4 decision 11 (turn 3, visits=64, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Basic {P} Energy (attackId=None)

### MCTS:[ABILITY] vs V6:[EVOLVE]
- Occurrences: 13 | In games V17 lost: 12 | Win rate when this diverged: 7.7%
- Of these, backed by a rollout that hit a terminal reward: 8/13 (61.5%)
  - game 11 decision 20 (turn 9, visits=61, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 12 decision 60 (turn 9, visits=59, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 22 decision 38 (turn 9, visits=59, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played Dragapult ex (attackId=None)

### MCTS:[ATTACH] vs V6:[ABILITY]
- Occurrences: 12 | In games V17 lost: 9 | Win rate when this diverged: 25.0%
- Of these, backed by a rollout that hit a terminal reward: 7/12 (58.3%)
  - game 2 decision 52 (turn 9, visits=159, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 4 decision 13 (turn 5, visits=57, hit_terminal=False): MCTS played Basic {R} Energy (attackId=None) | V6 would have played None (attackId=None)
  - game 5 decision 33 (turn 9, visits=58, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[RETREAT] vs V6:[ABILITY]
- Occurrences: 11 | In games V17 lost: 9 | Win rate when this diverged: 18.2%
- Of these, backed by a rollout that hit a terminal reward: 9/11 (81.8%)
  - game 2 decision 15 (turn 5, visits=77, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=None)
  - game 9 decision 43 (turn 9, visits=70, hit_terminal=True): MCTS played None (attackId=None) | V6 would have played None (attackId=None)
  - game 26 decision 34 (turn 7, visits=65, hit_terminal=False): MCTS played None (attackId=None) | V6 would have played None (attackId=None)

### MCTS:[ATTACH] vs V6:[EVOLVE]
- Occurrences: 11 | In games V17 lost: 9 | Win rate when this diverged: 18.2%
- Of these, backed by a rollout that hit a terminal reward: 7/11 (63.6%)
  - game 8 decision 9 (turn 5, visits=81, hit_terminal=True): MCTS played Basic {R} Energy (attackId=None) | V6 would have played Dragapult ex (attackId=None)
  - game 11 decision 8 (turn 5, visits=71, hit_terminal=True): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Drakloak (attackId=None)
  - game 11 decision 30 (turn 9, visits=61, hit_terminal=False): MCTS played Basic {P} Energy (attackId=None) | V6 would have played Dragapult ex (attackId=None)

## PLAY-vs-EVOLVE Card Tally (which card MCTS chose to play instead of evolving)

### Cards played in games V17 LOST

- Night Stretcher: 5
- Buddy-Buddy Poffin: 2
- Crispin: 2
- Ultra Ball: 2
- Dreepy: 2
- Crushing Hammer: 1
- Fezandipiti ex: 1
- Poké Pad: 1
- Lillie's Determination: 1

### Cards played in games V17 WON

- Budew: 2
- Lillie's Determination: 2
- Crispin: 1
- Poké Pad: 1
- Night Stretcher: 1
- Fezandipiti ex: 1
- Ultra Ball: 1

## Raw Data

- Per-decision: `results\v17_divergence\raw_decisions.jsonl`
- Per-game: `results\v17_divergence\raw_games.jsonl`