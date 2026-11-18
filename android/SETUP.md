# Media Manager companion (Android): one-time setup

## 1. Install the app
1. On the phone or tablet (Android 11 or newer), open the latest **android-…** release on GitHub and download
   `MediaManager-companion.apk`.
2. Open it. Android asks once to allow installing apps from your browser: allow it, then **Install**.
3. Open **Media Manager**, tap **Allow access** and turn on **Allow access to manage all files**
   (the app changes only the photos you pick).

## 2. Let it reach your OneDrive (about 5 minutes, once)
Microsoft only lets an app into your OneDrive with an "app ID" you create for it:

1. On a computer, go to <https://entra.microsoft.com> and sign in with the **same Microsoft account as your
   OneDrive**. (If it asks to set up a free Azure account or directory first, follow it: it's free.)
2. **App registrations** → **New registration**.
   - Name: `Media Manager companion`
   - Supported account types: **Personal Microsoft accounts only**
   - Redirect URI: leave empty → **Register**.
3. Copy the **Application (client) ID** (looks like `1a2b3c4d-…`).
4. Left menu: **Authentication** → at the bottom, **Allow public client flows** → **Yes** → **Save**.
5. In the app: **⚙** → paste it into **Microsoft app ID** → **Sign in to OneDrive** → it shows a code; tap
   **Copy the code and open the page**, paste the code, sign in and **Accept**.

Optional: put the ID in the GitHub repository as a **variable** named `ONEDRIVE_CLIENT_ID`
(Settings → Secrets and variables → Actions → Variables) and new versions have it built in.

## 3. Keep updates installing over the old version
Add two repository **secrets** (Settings → Secrets and variables → Actions → **New repository secret**):

| Name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the long text from `keystore-base64.txt` |
| `ANDROID_KEYSTORE_PASSWORD` | the text from `keystore-password.txt` |

(Claude gave you those two files. Without them, each version is signed with a different temporary key, so a new
version must replace the old one by uninstalling it first.)

## How the sync works
Every change you make on the phone (keywords, labels, ⭐/🔖, dates, names, edits, deletes) is made to the photo
on the phone straight away, and the same change is queued for the photo in **OneDrive › Pictures › Camera Roll**
(found by its name, or by its date taken if it was renamed on the PC). The app downloads that copy, makes the
same change and uploads it, so your PC gets it through OneDrive, keeping anything you did to it on the PC.
Changes wait (⚙ shows them) until you're online and the camera upload has put the photo in OneDrive.
Deletes go to OneDrive's recycle bin, so they can be restored there.

Keyword sets and the rename pattern come from the PC: Media Manager on the PC keeps them in
**OneDrive › Media Manager › companion.json**.
