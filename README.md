# Sales Onboarding Hub

Static site for the TLDR sales onboarding hub (schedule, reference data, resources, exercises, SMEs).

## Repository

Remote: [https://github.com/elyse16/ae-onboarding](https://github.com/elyse16/ae-onboarding)

## Publish with GitHub Pages

1. From this folder on your machine (first time only: add remote and push):

```bash
cd "/Users/elysewolin/Documents/People/Sales Onboarding"
git remote add origin https://github.com/elyse16/ae-onboarding.git
git push -u origin main
```

If `origin` already exists with a different URL:

```bash
git remote set-url origin https://github.com/elyse16/ae-onboarding.git
git push -u origin main
```

2. On GitHub: **Settings → Pages → Build and deployment → Source**: choose **Deploy from a branch**, branch **main**, folder **/ (root)**.
3. After a minute, the site will be at **https://elyse16.github.io/ae-onboarding/**.

To update the hub, replace `index.html` with a new export, commit, and push.
