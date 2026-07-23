# NFL 2026 season-prop normalization methodology

## Outputs

- `nfl_2026_season_props_normalized_-110_2026-07-19.csv` contains one
  normalized Over row and one normalized Under row for each
  sportsbook/player/market.
- `nfl_2026_season_props_unified_2026-07-19.csv` contains one cross-sportsbook
  consensus row per player/market, including every contributing sportsbook's
  normalized line.

The original source CSV is not modified.

## Player-name reconciliation

Before building the unified file, punctuation and capitalization differences
are reconciled deterministically (for example, `C.J. Stroud` and `CJ Stroud`).
The source also contains `Tetairoa McMilan` alongside the more common
`Tetairoa McMillan`; the matching market and overlapping lines identify this
as the same player. The normalized file keeps both a canonical `player` and
the original `source_player` for auditability.

## 1. Convert American odds to implied probabilities

For American odds \(A\):

\[
p(A)=
\begin{cases}
\frac{|A|}{|A|+100}, & A<0 \\
\frac{100}{A+100}, & A>0
\end{cases}
\]

Example: -120 implies \(120/(120+100)=0.5454545\), while +100 implies
\(100/(100+100)=0.5\).

## 2. Remove the sportsbook hold from every two-way market

Let \(p_O\) and \(p_U\) be the raw implied Over and Under probabilities. The
proportional no-vig probabilities are:

\[
q_O=\frac{p_O}{p_O+p_U}, \qquad
q_U=\frac{p_U}{p_O+p_U}=1-q_O
\]

The source overround/hold diagnostic stored in the normalized file is
\(p_O+p_U\). For an Over -120 / Under +100 market:

\[
q_O=\frac{0.5454545}{0.5454545+0.5}=0.5217391
\]

This step is necessary because setting the raw implied probability to 50%
would incorrectly ignore the sportsbook margin. A -110/-110 market has raw
implied probabilities of 52.38095% on both sides, but its no-vig probabilities
are exactly 50% and 50%.

## 3. Translate the no-vig probability into an even line

Odds alone identify a probability at the quoted line, but not how many yards,
receptions, touchdowns, or sacks the line should move. A probability
distribution is therefore required. This workflow uses a logistic survival
curve:

\[
P(X>L)=\frac{1}{1+\exp((L-\mu)/s)}
\]

where:

- \(L\) is the source line;
- \(\mu\) is the sportsbook's predicted 50th-percentile line;
- \(s\) is the line-sensitivity scale.

Solving the curve for \(\mu\):

\[
\mu=L+s\log\left(\frac{q_O}{1-q_O}\right)
\]

At \(L=\mu\), both no-vig sides equal exactly 50%. The normalized output
therefore publishes this new line with Over -110 and Under -110.

The sign is also economically consistent: when the no-vig Over probability is
above 50%, the even line moves higher; when it is below 50%, the even line moves
lower.

## 4. Calibrate line sensitivity from the source file

The source includes same-book alternate ladders. For every ladder point, the
Over probability is de-vigged using the median overround for the same
sportsbook and market. A linear fit is then applied to:

\[
\operatorname{logit}(q_O)=a+bL
\]

This gives \(s=-1/b\) and \(\mu=-a/b\).

The median fitted scale-to-line ratios from these ladders are used by market
family:

- Volume stats (passing/rushing/receiving yards and receptions):
  \(s/L=0.30594991142364136\).
- Low-count stats (passing/rushing/receiving touchdowns and sacks):
  \(s/L=0.44063243801941165\).

These ratios make the price-to-line conversion data-calibrated rather than an
arbitrary fixed rule such as “ten cents equals half a point.”

## 5. Treat one-sided alternate ladders separately

Eight DraftKings player/market groups contain only Over alternate selections
and no matching Under. They cannot be de-vigged point-by-point in the same way
as a two-way market.

For each of these groups:

1. The raw Over probability at each alternate line is divided by DraftKings'
   median overround for the same market.
2. A separate logistic line is fitted through all three or four ladder points.
3. The fitted 50th percentile becomes the normalized line.
4. A synthetic Over -110 and Under -110 pair is created.

These rows are explicitly marked
`one_sided_ladder_typical_hold_logistic_fit`. The remaining rows are marked
`paired_two_way_proportional_devig_logistic`.

## 6. Build the unified line

For a player/market with \(N\) contributing sportsbooks and normalized
sportsbook lines \(\mu_1,\ldots,\mu_N\), the unified line is the unweighted
arithmetic mean:

\[
\bar{\mu}=\frac{1}{N}\sum_{i=1}^{N}\mu_i
\]

Each sportsbook receives one vote. The unified CSV uses the resulting mean to
create one `bettable_line_nearest_half` column: touchdown markets are rounded
to the nearest whole number (half values round upward), while every other
market is rounded to the nearest half-point. The exact individual sportsbook
lines, minimum, maximum, range, and population standard deviation remain
available for auditability. The unrounded mean is intentionally omitted.

This is a cross-book consensus estimate. It is not a guarantee of a risk-free
betting arbitrage, because actual executable prices, limits, timing, and line
differences still matter.

## Reproduction

Run:

```bash
python3 normalize_nfl_2026_season_props.py
```

The script validates that every normalized sportsbook prop has exactly one
Over and one Under, every normalized price is -110, and every unified line
equals the mean of its available sportsbook lines.
