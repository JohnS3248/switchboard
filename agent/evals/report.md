# Switchboard agent evals

Model: `claude-opus-5` · 20/20 passed · p50 8927.1 ms · p95 13622.5 ms · tokens in/out 95528/9089

| id | pass | tools | rounds | latency ms | failures |
|---|---|---|---|---|---|
| s01 | ✅ | lookup_record | 2 | 6658.4 |  |
| s02 | ✅ | lookup_record → calculate → write_back | 4 | 13622.5 |  |
| s03 | ✅ | lookup_record → calculate | 3 | 8681.3 |  |
| s04 | ✅ | lookup_record → calculate → calculate | 3 | 10501.4 |  |
| s05 | ✅ | lookup_record → lookup_record → calculate → calculate | 3 | 12436.1 |  |
| s06 | ✅ | lookup_record → lookup_record → write_back | 3 | 8914.8 |  |
| s07 | ✅ | lookup_record | 2 | 5500.1 |  |
| s08 | ✅ | lookup_record → lookup_record → calculate | 3 | 11488.4 |  |
| s09 | ✅ | lookup_record | 2 | 5529.1 |  |
| s10 | ✅ | lookup_record → calculate → calculate | 3 | 12922.7 |  |
| s11 | ✅ |  | 1 | 2920.9 |  |
| s12 | ✅ | lookup_record → calculate | 3 | 7879.3 |  |
| s13 | ✅ |  | 1 | 5031.0 |  |
| s14 | ✅ | lookup_record → lookup_record → calculate | 3 | 10566.3 |  |
| s15 | ✅ | lookup_record → calculate → calculate | 3 | 14129.9 |  |
| s16 | ✅ | lookup_record → lookup_record → calculate → calculate | 4 | 13246.2 |  |
| s17 | ✅ |  | 1 | 8939.4 |  |
| s18 | ✅ |  | 1 | 7125.4 |  |
| s19 | ✅ | lookup_record → lookup_record → write_back | 3 | 10843.3 |  |
| s20 | ✅ |  | 1 | 3241.3 |  |
