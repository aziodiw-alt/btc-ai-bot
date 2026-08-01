# btc-ai-bot
My personal AI crypto assistant

## Strategy modes

- `Swing`: existing 1D + 4H mode.
- `Fast`: existing 4H + 1H mode.
- `Alpha`: optional conservative 1D + 4H pullback mode.

Alpha does not modify Swing or Fast. It blocks entries during sharp upward
momentum, separates live price from planned entries, staggers entries as
20% / 30% / 50%, avoids round-number order prices, and activates a
profit-protecting trailing plan only after TP1.

Use Alpha in the dashboard strategy selector. In Telegram, use `/alpha`
for BTC or `/alpha eth` for ETH.
