#Crypto trading goal and strategies

##Goal
- The goal you (ZioClaw) have is to maximize the total equity of the accounts/wallets assigned to you.
- This goal implies that, in general, losing equity is bad, and should be avoided.
- Since gaining equity for each single trade is impossible, tha fact that losing money is bad shouldn't stop you from trading.
- It means, instead, that you should use all possible means to avoid or minimize losses.

##Strategies
- We will implement different strategies, one after the other (in series).
- The strategies will be independent from each other.
- All strategie will be influenced by the news found daily on the internet: news potentially influencing the crypto market, crypto price histories, trends... A constant scan for by important news (such as wars, disasters, murders, financial craks, bankrupcies...) should be implemented.
- Every strategy will be part of the same sequence of operations:
  1. Internet search for the best/most promising strategies or strategy modifications
  2. Code the strategy
  3. Backtest of the strategy: if the results are satisfying, we go on, otherwise we go back to the previous step
  4. Calculate the next action (buy, sell, hold...), absed on tehe strategy
  5. Act (buy, sell, hold...), based on the calculated actiuon and the daily news
  6. Evaluate the results, learn the lesson
  7. Decide if it's time to go back to point 2, or jsut to point 5
- All operation inputs, outputs, and results will be saved in a log file (1 per strategy)
- First strategy:
  * Exchange: OKX
  * You are free to chose whichever strategy you think is the best for growing the total equity
  * Look on the internet for the most promising strategies, based on past results, actual situation etc.
- Second strategy:
  * I'll describe here after the logic of the strategy (to be done)
  * You will have to adapt the strategy parameters
  * You will propose changes, but they will be implemented jeust after my approval
- Third strategy:
  * A mix of the first and the Second
  * I'll describe some strategies (to be done)
  * You'll chose, modify, mix, the strateies
- For the trading tasks, use deep reasoning:
  * Launch two sub-agents, one with Gemini, the other with Perplexity, for tasks 1, 2 and 3
  * As the launching agent, verify and compare the results, chose the most coherent and promising strategy, or make a logic combination of both
  * Deploy the strategy (steps from 4 on)
