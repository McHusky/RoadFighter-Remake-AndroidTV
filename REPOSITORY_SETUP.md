# New GitHub repository setup

Create a new empty GitHub repository, then from this directory:

```bash
git init
git branch -M main
git add .
git commit -m "Initial Android TV source release"
git remote add origin git@github.com:YOUR_ACCOUNT/roadfighter-remake-android-tv.git
git push -u origin main
```

Before the first version tag, create one private release keystore and add the four Actions secrets documented in `README.md`.

Then publish the first release:

```bash
git tag -a v1.0.0 -m "Road Fighter Remake Android TV v1.0.0"
git push origin v1.0.0
```

The tag-triggered GitHub Actions job creates the GitHub Release and uploads the signed APK plus its SHA-256 checksum.
