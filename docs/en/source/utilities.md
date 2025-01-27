# Utilities

tpov comes with some utility scripts to help with data and video processing.

## tpov_combine.py

This program combines multiple video segments into a single video using metadata to determine the order and spacing. Any gaps in time between segments will be preserved in order to match with GPS data. **Please run `tpov_combine.py -h` for usage information and an important warning about video formats.**

## fetch_keys.py

This program fetches publically available Tianditu and Baidu Maps API keys for use with the `tpov_match` visualization basemap and the Baidu Maps `tpov_extract` data source respectively. Just run `python fetch_keys.py` and the keys will be printed to the terminal.

**Please run the following commands (in the tpov virtual environment if applicable) to install the dependencies for this script:**

```bash
pip install playwright
playwright install chromium-headless-shell
```

See the [Playwright documentation](https://playwright.dev/python/docs/library) for more information.

## [tpov_extract_visu](https://www.npmjs.com/package/tpov_extract_visu)

This is a Node.js package (not distributed with tpov) that helps visualize the JSON files created by `tpov_extract` on a map. Further information can be found on the npm page.