# BTC Scalp Bot — MT5 (Fusion Markets Demo)

## ⚠️ Reyalite anvan ou kòmanse
Pa gen bot ki ka garanti 80% win rate. Estrateji sa a (EMA crossover + RSI + ATR)
se yon apròch ki reyalis e teste nan endistri a, ki ka bay yon **edge** (avantaj
statistik) sou tan long — pa yon garanti pou chak jou. Objektif reyalis:
45-58% win rate ak yon reward:risk ~1:1.6, sa ki ka rantab si w swiv règ yo.

Risk 2%+ pa trade ou te chwazi a se **agresif**. Bot la gen yon "circuit breaker"
ki kanpe l otomatikman si:
- Ou pèdi 6% nan balans jounen an (`max_daily_loss_percent`)
- Ou fè 15 trade nan yon jou (`max_daily_trades`)

Ou ka ajiste chif sa yo nan `CONFIG` anlè fichye a.

## Enstalasyon (sou Windows, kote MT5 enstale)

```bash
pip install MetaTrader5 pandas numpy
```

**Enpòtan**: package `MetaTrader5` la mache SÈLMAN sou Windows, paske li konekte
dirèkteman ak terminal MT5 lokal la. Ou dwe:

1. Enstale MT5 desktop app (soti nan Fusion Markets)
2. Login sou kont **demo** ou a nan app la
3. Kite MT5 louvri
4. Lanse `btc_scalp_bot.py` nan menm machin nan

## Kijan estrateji a fonksyone

1. **Filtè tandans (M5)**: Bot la gade si EMA9 pi wo pase EMA21 sou M5 pou
   detèmine tandans jeneral la (BUY oswa SELL).
2. **Siyal antre (M1)**: Bot la tann yon "crossover" EMA9/EMA21 sou M1 ki ale
   nan menm direksyon ak tandans M5 la.
3. **Filtè RSI**: Evite antre nan zòn overbought/oversold ekstrèm.
4. **Filtè volatilite (ATR)**: Si mache a twò kalm (chòp), bot la pa antre —
   pa gen bon opòtinite nan mache san mouvman.
5. **Stop Loss / Take Profit**: Kalkile otomatikman ak ATR (1.2x pou SL,
   2.0x pou TP), pou adapte ak volatilite aktyèl la.
6. **Lajistman pozisyon**: Chak trade riske egzakteman 2% balans ou, kalkile
   otomatikman selon distans SL la.

## Anvan ou mete kòb reyèl

1. **Teste sou demo pou 4-6 semèn minimòm** — kite bot la travay, pa touche l.
2. **Revize `trade_log.csv`** chak semèn: gade win rate reyèl, pi gwo pèt
   konsekitif, ak si estrateji a rantab apre spread/kòmisyon Fusion Markets.
3. **Backtest** — mwen ka bati yon script backtest separe si ou vle teste
   estrateji a sou done istorik anvan ou menm lanse l sou demo live.
4. Si w vle diminye risk pita, chanje `risk_percent` nan CONFIG a (pa egzanp
   1.0 oswa 0.5).

## Fichye ki jenere
- `trade_log.csv` — istorik tout trade bot la fè (dat, direksyon, lot, pri, SL, TP)
