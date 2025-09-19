# How to Use Cookies for Private or Age-Gated Content

This guide explains how to export your browser cookies so YMDE can download content that isn't publicly available, such as age-restricted or private videos.

**Security Note**: Your `cookies.txt` file contains sensitive session information. Treat it like a password and do not share it.

### Step 1: Get a Browser Extension

You need an extension that can export cookies in the "Netscape" format. A popular choice is **Get cookies.txt** (available for [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid) and [Firefox](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt/)).

### Step 2: Export Your Cookies

1.  Make sure you are logged into your YouTube/Google account in your browser.
2.  Go to `www.youtube.com`.
3.  Click the "Get cookies.txt" extension icon in your browser's toolbar and click **Export**. This will copy the cookie data to your clipboard.

### Step 3: Create the `cookies.txt` File

1.  Create a new text file named `cookies.txt` inside your local `./data` folder.
2.  Paste the copied cookie data into this file and save it.

### Step 4: Update Your `compose.yml`

Uncomment the `COOKIES` line in your `compose.yml` file to enable it:

```yaml
services:
  ymde:
    # ... other settings
    environment:
      # ...
      # - DRY_RUN=1                 # 1=Simulate without downloading, 0=disable
      - COOKIES=/data/cookies.txt # Path to cookies file for private/gated content.
```

Now, when you run the downloader, it will use your login session to access content.
