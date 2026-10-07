# Apartment watcher

Get an email for every new rental apartment in the city of Amsterdam listed on Vestim (vestim.nl) and MVGM (ikwilhuren.nu).
It checks every 10 minutes while your Mac is awake and you are logged in.
The first check only remembers existing listings, so you won't get a flood of emails.

1. **Get ready.** You need a Gmail account with 2-Step Verification turned on.
   Create a [Gmail App Password](https://myaccount.google.com/apppasswords) and keep it handy for setup.
   For the optional auto-apply preview, you also need a free ikwilhuren.nu account.

2. **Download the project.** On this GitHub page, click the green **Code** button, then **Download ZIP**.
   Double-click the ZIP file to unzip it. Open the unzipped folder.

3. **Install.** You need an internet connection the first time; downloading the tools it needs can take a few minutes.
   Double-click **Install.command**. If macOS says it can't verify it, click **Done**.
   Open **System Settings > Privacy & Security**, scroll down, and click **Open Anyway** next to **Install.command**.
   Confirm with your password or Touch ID, then click **Open**. You only need to do this the first time.
   If macOS asks whether Terminal may access files in your Downloads folder, click **Allow** so the installer can copy itself out of that folder.
   Answer the questions in the window. Use your Gmail App Password when asked.
   Nothing shows on screen when you type or paste a password—that's normal. Just paste it and press Return.
   You can paste the Gmail App Password with or without spaces.

4. **Choose where to receive emails.** The setup window asks “Which email address should receive the apartment emails”.
   You can use any email address, not just Gmail. It defaults to your Gmail address; press Return to keep it.
   The test email goes to that address. Check its inbox. To change the address later, run **Install.command** again.

5. **Choose the optional auto-apply preview.** This is currently only a preview, called “shadow” mode.
   Emails are marked **[Would apply]** when an MVGM apartment fits your maximum rent, minimum size and income.
   Leave a new limit empty for no limit. When running **Install.command** again, type `-` to remove a saved limit.
   MVGM requires a gross yearly household income of about 45 times the monthly rent for 1 person, or 60 times for 2 or more.
   Actually submitting applications is not available yet.

6. **Keep it running.** The watcher runs in the background, restarts by itself if it crashes, and starts again when you log in after a restart.
   It only works while your Mac is awake and you are logged in. Closing the lid or putting your Mac to sleep pauses it until it wakes up.
   Keep your Mac plugged in.
   When macOS shows **“Background Items Added”**, that's the watcher. Leave it allowed in **System Settings > General > Login Items & Extensions**; switching it off stops the watcher.
   If emails keep failing, you get a Mac notification titled **“Apartment watcher”** telling you to run **Install.command** again.
   You get an email if a website seems broken, or if a site has no Amsterdam rentals for about a day (that can be normal).

7. **Change settings.** Run **Install.command** again. It remembers your answers.

8. **See what it's doing.** In Finder, choose **Go > Go to Folder**.
   Paste `~/Library/Application Support/apartment-watcher` and press Return.
   Open **watcher.log** to see recent activity.
   Its full location is `~/Library/Application Support/apartment-watcher/watcher.log`.

9. **Stop and remove it.** Open **Uninstall.command** the same way as **Install.command**.

10. **If something seems wrong:**
    No test email? Check the receiving address, your Gmail address and App Password. Use the App Password, not your usual Gmail password.
    No apartment emails for a while? That's normal when nothing new is listed. Check the log, and make sure your Mac is awake and you are logged in.
    An email with **“scraper may be broken”** in the title means the watcher repeatedly couldn't check a website. The site may have changed, and the watcher may need an update.
