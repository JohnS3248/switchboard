# Switchboard agent evals

Model: `claude-opus-5` · 17/20 passed · p50 8506.0 ms · p95 14025.9 ms · tokens in/out 90676/8820

| id | pass | tools | rounds | latency ms | failures |
|---|---|---|---|---|---|
| s01 | ✅ | lookup_record | 2 | 6700.5 |  |
| s02 | ✅ | lookup_record → write_back → calculate | 4 | 13543.5 |  |
| s03 | ✅ | lookup_record | 2 | 7505.5 |  |
| s04 | ❌ | lookup_record → calculate → calculate | 3 | 10303.3 | category: expected 'refund', got 'complaint' |
| s05 | ✅ | lookup_record → lookup_record → calculate → calculate | 3 | 10187.0 |  |
| s06 | ✅ | lookup_record → write_back | 3 | 7388.7 |  |
| s07 | ✅ | lookup_record | 2 | 5179.3 |  |
| s08 | ✅ | lookup_record → lookup_record → calculate | 3 | 10230.2 |  |
| s09 | ✅ | lookup_record | 2 | 5497.7 |  |
| s10 | ✅ | lookup_record → calculate → calculate | 3 | 11962.5 |  |
| s11 | ✅ |  | 1 | 6207.7 |  |
| s12 | ✅ | lookup_record → calculate | 3 | 7047.4 |  |
| s13 | ✅ |  | 1 | 4914.4 |  |
| s14 | ❌ | lookup_record → lookup_record → calculate | 3 | 9506.4 | category: expected 'order_status', got 'enquiry'; needs_human: expected False, got True |
| s15 | ✅ | lookup_record → calculate | 3 | 15293.2 |  |
| s16 | ✅ | lookup_record → lookup_record → calculate → calculate | 3 | 14025.9 |  |
| s17 | ❌ |  | 1 | 13429.6 | needs_human: expected False, got True |
| s18 | ✅ |  | 1 | 5573.9 |  |
| s19 | ✅ | lookup_record → lookup_record → write_back → calculate | 3 | 11944.0 |  |
| s20 | ✅ |  | 1 | 3236.2 |  |
