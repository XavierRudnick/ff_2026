# 2026 PPR consensus ranking sources

Generated on **2026-07-26**. The output is
`rankings/ppr_consensus_2026-07-26.csv`.

## Included rankings

| CSV column | Publisher and ranking | Rows used | Source freshness |
| --- | --- | ---: | --- |
| `espn_rank` | [ESPN PPR Top 300](https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300) | 300 | PDF updated 2026-07-23 |
| `cbs_rank` | [CBS Sports PPR Top 200 consensus](https://www.cbssports.com/fantasy/football/rankings/ppr/top200/) | 200 | Page said “Updated 1d ago” when retrieved |
| `yahoo_rank` | [Yahoo Sports consensus Top 300](https://sports.yahoo.com/fantasy/article/fantasy-football-rankings-consensus-top-300-players-160643696.html) | 300 | Published 2026-07-15 |
| `footballguys_rank` | [Footballguys 2026 PPR draft rankings](https://www.footballguys.com/rankings) | 300 | Retrieved 2026-07-26 |
| `rotoballer_rank` | [RotoBaller 2026 overall PPR rankings](https://www.rotoballer.com/nfl-fantasy-football-rankings-tiered-ppr/265860/rankings?spreadsheet=ppr&league=Overall) | 300 | Retrieved 2026-07-26 |
| `fantasypros_rank` | [FantasyPros 2026 PPR consensus](https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php) | 25 | Consensus updated 2026-07-26 |
| `draftsharks_rank` | [Draft Sharks 2026 PPR rankings](https://www.draftsharks.com/rankings/ppr) | 25 | Reviewed 2026-07-25 |

FantasyPros and Draft Sharks exposed only their first 25 rows on their public
pages. Their remaining cells are intentionally blank. No paywall was bypassed.
Yahoo's live widget returned more than 300 rows, but only the advertised top 300
were used so its depth matched the other deep boards.

## Merge rules

- `average_rank` is the arithmetic mean of the nonblank publisher ranks on that
  row, rounded to two decimals.
- A missing rank is not converted to 301 or otherwise penalized.
- `sources_ranked` reports the number of ranks used in the average.
- `consensus_rank` orders all rows by `average_rank`, then by greater source
  coverage, then alphabetically.
- The file is a union: a player ranked by at least one included source remains
  in the CSV. For a higher-confidence shortlist, filter to
  `sources_ranked >= 3`.

## Name reconciliation

Names are Unicode-normalized and compared without punctuation, spacing, or
generational suffixes. Known equivalents such as **Ken/Kenneth Walker**,
**Kenny/Kenneth Gainwell**, initials such as **A.J./AJ**, and all NFL team
defense naming styles are merged.

The ESPN PDF text layer contained eight clear OCR errors. They were
conservatively fuzzy-matched against the other boards using position when
available. Every source was also checked for contiguous ranks and duplicate
normalized players before the CSV was written.

The reproducible parser is `scripts/build_2026_ppr_consensus.py`. Its raw web
snapshots are kept locally under the gitignored `.firecrawl/` directory.
