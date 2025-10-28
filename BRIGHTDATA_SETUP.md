# 🔐 Bright Data Setup Guide

## Problem
Your current `BRIGHTDATA_API_KEY` format isn't working (getting 407 Invalid Auth).

## Solution: Get the Correct Credentials

### Step 1: Log into Bright Data Dashboard
Go to: https://brightdata.com/cp

### Step 2: Create a Web Unlocker Zone

1. Click "**Proxies & Scrapers**" in left menu
2. Click "**Add zone**"
3. Select "**Web Unlocker**"
4. Give it a name (e.g., "news-scraper")
5. Click "**Add**"

### Step 3: Get Your Zone Credentials

After creating the zone, you'll see:
- **Username** (looks like: `brd-customer-hl_12345678-zone-news_scraper`)
- **Password** (random string)
- **Host**: `brd.superproxy.io`
- **Port**: `22225` or `33335`

### Step 4: Update Your .env File

```bash
cd /home/jarvis/projects/marico-news-sumamrizer/api
nano .env
```

**Replace:**
```
BRIGHTDATA_API_KEY=079fbf07ab9ef16d3752510288ec754a11dc94c9abf6a54a2efbbfbc44c35c34
```

**With** (use YOUR credentials):
```
BRIGHTDATA_USERNAME=brd-customer-hl_YOUR_ID-zone-YOUR_ZONE
BRIGHTDATA_PASSWORD=YOUR_PASSWORD_HERE
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=22225
```

### Step 5: Test the Connection

```bash
cd api
source benv/bin/activate
curl --proxy brd-customer-hl_YOUR_ID-zone-YOUR_ZONE:YOUR_PASSWORD@brd.superproxy.io:22225 https://httpbin.org/ip
```

If you see JSON with an IP address, it's working!

---

## Alternative: If You Have Scraping Browser

If you purchased **Scraping Browser** instead of Web Unlocker:

1. Go to dashboard → Scraping Browser
2. Get your API token
3. The current format might work, but use this format in .env:
```
BRIGHTDATA_API_TOKEN=YOUR_TOKEN_HERE
```

---

## Quick Test After Setup

```bash
cd api
python3 test_brightdata.py
```

Should show:
```
✅ SUCCESS!
HTML Length: 50,000+ bytes
🎉 Bright Data is working perfectly!
```

---

## Need Help Finding Credentials?

Look for this in your Bright Data dashboard:
1. Left menu → "**Proxies & Scrapers**"
2. Click on your zone name
3. See "**Access parameters**" section
4. Copy Username and Password

---

## Expected Format

Your username should look like:
```
brd-customer-hl_a1b2c3d4-zone-yourzone
```

NOT just a random token!

---

Once you have the correct format, we'll update the code and test again! 🚀

