# Switchboard agent evals (langgraph)

Model: `claude-opus-5` · 20/20 passed · p50 8257.3 ms · p95 13213.6 ms · tokens in/out 87259/8527

| id | pass | tools | rounds | latency ms | failures |
|---|---|---|---|---|---|
| s01 | ✅ | lookup_record | 2 | 6219.1 |  |
| s02 | ✅ | lookup_record → write_back | 3 | 8300.2 |  |
| s03 | ✅ | lookup_record | 2 | 6318.6 |  |
| s04 | ✅ | lookup_record → calculate → calculate | 3 | 12704.7 |  |
| s05 | ✅ | lookup_record → lookup_record → calculate → calculate | 3 | 10042.4 |  |
| s06 | ✅ | lookup_record → write_back → write_back | 4 | 15912.6 |  |
| s07 | ✅ | lookup_record | 2 | 5223.8 |  |
| s08 | ✅ | lookup_record → lookup_record | 2 | 8816.0 |  |
| s09 | ✅ | lookup_record | 2 | 5866.8 |  |
| s10 | ✅ | lookup_record → calculate → calculate | 3 | 11894.6 |  |
| s11 | ✅ |  | 1 | 3421.6 |  |
| s12 | ✅ | lookup_record → calculate | 3 | 8214.4 |  |
| s13 | ✅ |  | 1 | 4464.3 |  |
| s14 | ✅ | lookup_record → lookup_record | 2 | 10390.3 |  |
| s15 | ✅ | lookup_record → calculate | 3 | 11048.3 |  |
| s16 | ✅ | lookup_record → lookup_record → calculate → calculate | 4 | 13213.6 |  |
| s17 | ✅ |  | 1 | 7728.8 |  |
| s18 | ✅ |  | 1 | 5236.4 |  |
| s19 | ✅ | lookup_record → lookup_record → write_back | 3 | 10536.9 |  |
| s20 | ✅ | calculate | 2 | 5153.6 |  |
