# Apartment watcher

Get an email for every new rental apartment in the city of Amsterdam listed on Vestim (vestim.nl) and MVGM (ikwilhuren.nu).
It checks every 10 minutes while your Mac is on.
The first check only remembers existing listings, so you won't get a flood of emails.

1. **Get ready.** You need a Gmail account with 2-Step Verification turned on.
   Create a [Gmail App Password](https://myaccount.google.com/apppasswords) and keep it handy for setup.
   For the optional auto-apply preview, you also need a free ikwilhuren.nu account.

2. **Download the project.** On this GitHub page, click the green **Code** button, then **Download ZIP**.
   Double-click the ZIP file to unzip it. Open the unzipped folder.

3. **Install.** Right-click **Install.command**, then choose **Open**.
   Use right-click the first time because macOS blocks downloaded scripts.
   Answer the questions in the window. Use your Gmail App Password when asked.
   You'll get a test email. Check your inbox.
   The watcher then runs in the background. It starts again when you log in after a restart.

4. **Choose the optional auto-apply preview.** This is currently only a preview, called “shadow” mode.
   Emails are marked **[Would apply]** when an MVGM apartment fits your maximum rent, minimum size and income.
   MVGM requires a gross yearly household income of about 45 times the monthly rent for 1 person, or 60 times for 2 or more.
   Actually submitting applications is not available yet.

5. **Change settings.** Run **Install.command** again. It remembers your answers.

6. **See what it's doing.** In Finder, choose **Go > Go to Folder**.
   Paste `~/Library/Application Support/apartment-watcher` and press Return.
   Open **watcher.log** to see recent activity.
   Its full location is `~/Library/Application Support/apartment-watcher/watcher.log`.

7. **Stop and remove it.** Right-click **Uninstall.command**, then choose **Open**.

8. **If something seems wrong:**
   No test email? Check your Gmail address and App Password. Use the App Password, not your usual Gmail password.
   No apartment emails for a while? That's normal when nothing new is listed. Check the log, and make sure your Mac is on.
   An email titled **“scraper may be broken”** means a website changed and the watcher needs an update.
