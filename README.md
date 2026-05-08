# Sales Onboarding Hub

Static site for the TLDR sales onboarding hub (schedule, reference data, resources, exercises, SMEs).

## Publish with GitHub Pages

1. Create a new empty repository on GitHub (for example `sales-onboarding-hub`).
2. From this folder on your machine:

```bash
cd "/Users/elysewolin/Documents/People/Sales Onboarding"
git init
git add index.html README.md
git commit -m "Add Sales Onboarding Hub static site"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

3. On GitHub: **Settings → Pages → Build and deployment → Source**: choose **Deploy from a branch**, branch **main**, folder **/ (root)**.
4. After a minute, the site will be at `https://YOUR_USERNAME.github.io/YOUR_REPO/` (or your organization’s equivalent).

To update the hub, replace `index.html` with a new export, commit, and push.
