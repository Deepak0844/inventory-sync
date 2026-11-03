# Manual login uses a plain browser and reads its cookie file

A Supplier's CAPTCHA can reject a correct answer when the browser is driven by Playwright, because a driven browser reports itself as automated. So manual login starts Chromium as an ordinary program and attaches nothing to it. The cost is that the worker cannot watch the page, so the owner presses **Done** (or closes the window), and only then does the worker look at the result.

Two surprising details follow from that choice, both checked by hand in the real container image:

- **The browser is closed with SIGINT.** Chromium saves its cookies on SIGINT but drops the ones changed in the last ~30 seconds on SIGTERM, which is the login that just happened.
- **The profile's cookie file is read directly.** Chromium drops cookies that have no expiry when a profile is opened again, and many logins use them, so reopening the profile with Playwright loses the session. `app/flows/chromium_cookies.py` decrypts the file instead. That works only for Linux Chromium with `--password-store=basic` (a fixed key, no keyring), and only because the Chromium version is pinned by `uv.lock`; a Playwright upgrade must re-run the real-browser round trip.

Only cookies for the Supplier's own site are saved, because Chromium also makes background requests that leave other sites' cookies in the profile. Local storage is not saved. If a Supplier still rejects the CAPTCHA in a plain browser, the site does not want this login automated and the fix is a feed or written permission from the Supplier, not more disguise.
