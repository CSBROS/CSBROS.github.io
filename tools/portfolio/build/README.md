# 3-Month Basis Portfolio build

- `inputs.json`: the record. Daily official closes, every fill, IWM at each fill, deposits.
- `build.py`: computes returns and the IWM twin, writes `data.json` and `../index.html`.
- `template.html`: the page; `build.py` inlines the data.

To refresh: append the new trading days, fills and deposits to `inputs.json`, set `as_of`, run `python3 build.py`, commit.
