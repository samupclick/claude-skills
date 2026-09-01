# Circadian / Dough Labs LLC: Meta relaunch plan v2

Prepared 1 September 2026 for Sam Jones (UpClick Labs), after Jacob Katz's reply of 1 September 2026 to "Your Meta relaunch plan, as promised".

## 1. What Jacob's reply changed

Three facts in Jacob's reply invalidate the sequence in the 1 September plan.

1. **His personal Facebook is alive.** The account that died was a second Facebook login on jacob@circadianrest.com that held the admin role on the business portfolio. So the "recover your original account through facebook.com/hacked" step has nothing to recover. His original account is fine, and the dead one is past every appeal window.
2. **The June 2026 account was not killed as a duplicate of his personal account.** It was killed under Meta's ban-evasion rule, as a new account "created to evade a previous account removal" with "common ownership" with the disabled circadianrest.com login. That matters because it tells us which of Jacob's identities Meta has flagged: the business login, not the personal one.
3. **He is asking UpClick to create and own the new business portfolio.** That request needs an adversarial review of its own, because it recreates the exact failure that destroyed Circadian (one person's login as sole admin) and puts Sam's personal Facebook account, and therefore every UpClick client, inside the blast radius.

**Research limitation.** The network in this session blocks Meta's own domains, so every Meta quote below comes from search-engine excerpts of the cited Meta help articles rather than the live page. Quotes are marked by confidence. Before this goes to Jacob, open the five or six URLs that carry the plan (listed in section 9) and confirm the wording.

## 2. The account model, and where Jacob's confusion comes from

Meta has no such thing as a "business account" that a person logs into. Jacob's language on the call ("my business account") mixed up two different objects. The model:

| Object | What it is | Who can hold it | Jacob's status |
|---|---|---|---|
| Facebook personal account | A login and profile for one human. Meta's Terms: "Create only one account (your own)". | One per person | Personal account alive. Business-email login disabled 26 Apr 2025. June 2026 login disabled. |
| Business portfolio (formerly Business Manager) | A container that owns Pages, ad accounts, pixels, catalogs, Instagram accounts. Not a login. People are given roles in it from their personal account. | Created by a person's account; up to 2 per person by default | Portfolio 921971839686539 orphaned: it still exists as far as anyone can tell, but no living login has a role in it. |
| Facebook Page | The public business presence | Owned by a person or a portfolio | facebook.com/circadianrest shows "content isn't available". Page object still exists (Instagram still lists it). |
| Ad account | Billing and campaign container inside a portfolio. Permanently locked to the portfolio that created it. | Portfolio | 633704592556946, orphaned with the portfolio. |
| Pixel / dataset | Tracking asset, also locked to its portfolio | Portfolio | 1971038363401583, orphaned. |
| Instagram professional account | A separate login. Can be Page-connected and, separately, owned ("claimed") by a portfolio. | Its own login | @circadianrest alive, Page-connected to the dead Page. Whether the dead portfolio also owns it is unknown. |
| Accounts Center | Groups logins (Facebook profile, Instagram, Threads) for shared login and 2FA | Per person | Contains Instagram and Threads only. Correct. Keep it that way. |

What Jacob actually did in 2024 or earlier was create a second personal Facebook account on his business email and use it as the admin of the portfolio. Meta's Authentic Identity standard says accounts that "represent a non-human entity, such as a business" can be "permanently disabled", and the Terms say to create one account and use it "for personal purposes". So the business login was non-compliant from day one. That is background, not blame: it is how a large share of small businesses set themselves up before Meta introduced additional profiles and professional mode.

The practical consequence: **nobody can "recover the business account", because it was never the business. What is recoverable in principle is the orphaned portfolio, and only through a channel that reaches a human at Meta.**

## 2b. How to explain it to Jacob

Suggested wording, in Sam's voice, to sit at the top of the next email.

> Meta does not let a business log in. Every Page, ad account and Business Manager has to be run by a person, through that person's own Facebook account, and Meta allows each person exactly one. The company gets verified with documents and an EIN, but the company cannot act. A person acts for it. So the personal account is Meta's unit of trust: account age, payment history and every enforcement decision attach to the human, not to Dough Labs.
>
> That is why your setup failed in two directions. The login on jacob@circadianrest.com was a second account for one human, which Meta treats as inauthentic even when the human is real. When it was hacked and disabled, everything it administered was orphaned. When you built a fresh account in June, Meta recognised the same person behind a removed account and shut it as evasion. Passing the selfie did not help, because the selfie proves you are you, and "you" is what was flagged.
>
> Nobody is asked to prove they are human to create a Business Manager. Those checks only appear once Meta suspects something. What Meta weighs all the time is identity plus history: one account per person, how old it is, whether it has paid its bills, whether it has ever been enforced against.
>
> So the scarce thing is not a Business Manager. It is a person with one clean, established Facebook account who is willing to be the accountable human for Circadian. Your personal account is one. A co-owner's or partner's is another. Mine is a third, but if mine is the only one, Circadian is in the same shape it was in April 2025: one human's login between the business and nothing.

## 3. Adversarial review of Jacob's proposal (UpClick creates and owns the portfolio)

Tested against Meta's documents. Verdict: workable as a last resort, but it should not be the default, and never with Sam as sole admin.

| # | Finding | Meta source | Confidence |
|---|---|---|---|
| A1 | **It recreates the single point of failure.** One personal account as the only admin is exactly how Circadian lost everything. If Sam's login is ever disabled, hacked, or advertising-restricted, Dough Labs owns nothing on Meta and is back where it is today. | Meta's Business Support Home article: "The status of your Facebook account impacts your personal ad account and access to certain features for managing advertising assets." | High |
| A2 | **Ad account and pixel can never leave.** "If you create a new ad account in a business portfolio, it will permanently be a part of that portfolio, meaning the ad account can't be deleted or transferred." Pixels behave the same. Handing Circadian back later means handing over the whole portfolio, not extracting the assets. | facebook.com/business/help/915885887059947 | High |
| A3 | **Blast radius onto UpClick.** Meta's Account Integrity standard lets it act on "business assets that are created or repurposed to evade a previous account or entity removal, including those assessed to have common ownership and content as previously removed accounts". A new portfolio verified as Dough Labs LLC on circadianrest.com is, by design, the same business as the removed one. If Meta's systems link them and restrict "a person's advertising access", the person is Sam, and the restriction reaches UpClick's own portfolio and every client Sam administers. | transparency.meta.com Account Integrity; facebook.com/business/help/422289316306981 ("Meta can restrict an ad account, a person's advertising access, a Page, or a Business Account") | Medium for propagation (documented at person level, cross-portfolio effect is practitioner-reported) |
| A4 | **Verification can be refused or reversed on an authorisation ground.** Rejection reasons include "attempting to claim or verify a business portfolio that you don't own or have authorisation to represent". Mitigation is a signed agency authorisation from Dough Labs LLC and control of an @circadianrest.com mailbox or DNS. | facebook.com/business/help/2342133782492969 | Medium |
| A5 | **Liability sits with the portfolio owner.** Self-Serve Ad Terms: if "the advertiser you represent violates these Self-Serve Ad Terms... Meta may hold you responsible". Unpaid balances are owed by the portfolio that owns the ad account regardless of whose card is billed. | facebook.com/legal/self_service_ads_terms; facebook.com/business/help/3782924858467145 | High |
| A6 | **Portfolio cap.** A person can create about 2 portfolios; Meta's only documented remedy at the cap is deleting old ones. Sam may already be at the cap. | facebook.com/business/help/1710077379203657 (excerpt) | Medium |
| A7 | **The domain is probably still claimed by the dead portfolio.** "Domains can only be added to one business." The release path emails the owning portfolio's admins, who do not exist. Applies to every option, not only this one. Domain verification is a nice-to-have (link editing, some iOS event configuration), not a blocker for ads, pixel, Conversions API or the Shopify channel. | facebook.com/business/help/321167023127050 and community error text | High that the rule exists, Medium that the domain is claimed |

What Jacob got right: starting with a build rather than with recovery. Every Meta recovery channel is a logged-in surface, the original login is past its 180-day window, and there is no documented case of Meta support restoring a portfolio 16 months on. Recovery belongs on a parallel track (section 7), not on the critical path.

## 4. Adversarial review of the 1 September plan (Sam's own email)

Corrections to put in front of Jacob so the second plan is trusted.

1. **"Recover your original account through facebook.com/hacked" does not apply.** That flow is for live accounts under someone else's control. The disabled login was not appealable at the time, and its 180-day window closed around 23 October 2025. Meta's article: after 180 days or a failed appeal "your account will be permanently disabled and you won't be able to request another review".
2. **"Video-selfie verification works in your favour" was wrong.** Jacob passed the selfie and was disabled anyway. Meta's selfie compares you to "photos on your Facebook or Instagram profiles, including any previous profile photos"; it confirms you are you, and being you is the problem when the removed account was also you.
3. **"Each new account you made got killed because Meta allows one account per person" was half right.** The rule that fired was ban evasion. The distinction matters for the personal account: it predates everything and did not evade anything, so no published rule puts it at automatic risk. It becomes exposed only if it is used to rebuild the removed assets. That is a real but different risk, and it applies to whoever's account does the rebuilding.
4. **"Connect the Instagram to the new Page from your app, no access to old accounts needed" is right, with one caveat.** The Instagram-side flow asks you to "Login to Facebook" with an account that is an admin of the new Page. That is a one-time authorisation, not adding the Facebook account to Accounts Center. Decline the Accounts Center prompt if it appears.
5. **Step 4 ("check your advertising standing in Business Support Home and file the recovery request on the old Business Manager") cannot be done.** Business Support Home only shows portfolios the logged-in person has a role in.
6. **Everything else stands**: fresh build, currency and timezone set once, phone verification before the first ad, spending cap, 2FA for everyone, business verification early, small test ad, Shopify channel, and the scam warning about phone numbers.

## 5. Who should own the new portfolio

| Option | Who creates and admins | Isolation if Meta links the new business to the old | Compliance fit | Exit / handover | Verdict |
|---|---|---|---|---|---|
| **B1. A Dough Labs person other than Jacob** (co-owner, spouse, employee) with an aged, clean personal Facebook account, two admins from day one, UpClick as partner | Client | Best. Restriction lands on the client's portfolio and one non-Jacob login. | Meta's intended model: client owns, agency gets revocable partner access. | None needed. | **Recommended if such a person exists.** |
| **B2. Jacob's living personal account** creates it, second admin added immediately, UpClick as partner | Client | Good for UpClick. Exposes Jacob's last surviving Facebook identity. | Compliant. The personal account is his one permitted account. | None needed. | Recommended fallback. Jacob's reluctance is understandable but rests on a misdiagnosis (see section 4, point 3). His call. |
| **A. Sam's personal account creates a separate "Dough Labs LLC" portfolio**, verified as Dough Labs, Sam sole admin | UpClick | Poor. Portfolio-level isolation only; person-level restriction hits all UpClick clients. | Allowed with written authorisation, but the authorisation rejection ground applies. | Whole-portfolio handover; ad account and pixel never leave. | Last resort only, and only with a second admin and a written agreement. |
| **C. Circadian assets inside UpClick's existing verified portfolio** (agency-owned ad account, agency-owned Page) | UpClick | Worst for UpClick's other clients if their ad accounts live in the same portfolio: a portfolio restriction "impacts the ad accounts, shops and business assets they own". | Standard agency practice. | Page is transferable later; ad account and pixel are not. | Avoid unless UpClick's portfolio holds no other client assets. |

Recommendation to put to Jacob: **B1 if there is a second real person at Dough Labs; otherwise B2.** If Jacob refuses both, do A with the safeguards in section 6, phase 2, and say plainly that it reproduces the risk that already cost him the business once.

One more argument for B1 or B2 that Jacob will care about: the Shopify channel requires the connecting person to have "full control of the business portfolio and Facebook Page", and the portfolio "has to be the owner of the Facebook Page". Under option A, Dough Labs cannot connect its own store; only Sam can.

## 6. The plan

Every phase has a stop condition. Do not proceed past a stop condition without deciding what it means.

### Phase 0. Paperwork and hardening (Jacob, this week)

1. **Written agency authorisation** from Dough Labs LLC naming UpClick Labs as its agent for Meta advertising, signed by Jacob as managing member. Needed for business verification and for the Self-Serve Ad Terms "authority to bind the advertiser" warranty, whichever option is chosen.
2. **Formation documents and EIN letter** for Dough Labs LLC, with legal name, address and phone exactly as they will be entered in the portfolio. Meta rejects on mismatch: "the legal entity name in the submitted document must match the legal entity name you provided".
3. **A fresh payment card** that has never been on Meta. The card that carried the fraud stays off every Meta surface. This is precautionary; Meta does not document card-level flags, but a new instrument costs nothing.
4. **Instagram hardening.** Unique password, authenticator-app 2FA, review "Where you're logged in", download the account data. Confirm in Metricool whether the Instagram is connected by Instagram login or Facebook login. Leave the contact email alone: it has survived 16 months and changing it is a new signal for no gain.
5. **Confirm nobody creates any new Facebook account.** A fourth would be treated as evasion on sight.
6. **Ask Jacob the questions in section 8** so the ownership decision is made before anything is built.

### Phase 1. Canaries before anyone's account is committed (Sam and Jacob, one day)

1. **Instagram-app boost with no Facebook Page.** From the Instagram app, boost an existing post for $10 to a website-visits goal with the new card. Meta documents this as "Boost an Instagram post without a Meta ad account". No Facebook login is involved.
   - Pass: the Instagram, the domain in the link, and the new card are not blacklisted at the level that matters most.
   - Stop condition: if the boost is refused with an advertising restriction, the Instagram itself carries a restriction. That changes the plan entirely (a Meta Verified support case on the Instagram becomes step one) and nobody's Facebook account should be spent on a build until it is cleared.
2. **Instagram ownership probe** happens in phase 2, step 3, because it needs the new portfolio to exist.

### Phase 2. Build the portfolio (owner per section 5; Sam assists on a call)

1. The chosen person, from their own device and their normal browser, creates the business portfolio. Name: Dough Labs LLC. Business email: an @circadianrest.com mailbox they control (email verification is Meta's fastest route and doubles as the "connection to the business" proof).
2. **Add a second admin the same day.** Under B1 that is Jacob's personal account or Sam; under B2 it is a Dough Labs person or Sam; under A it is a Dough Labs person. Two admins is the entire lesson of the last sixteen months.
3. **Instagram ownership probe.** Business settings, Accounts, Instagram accounts, Add, log in as @circadianrest.
   - Success: the old portfolio only had a Page connection. The new portfolio now owns the Instagram. Continue.
   - "This Instagram account is already owned by another business": the dead portfolio claimed it. Meta's only documented remedies are the owner removing or transferring it, so this goes to the human-support track (phase 5). Ads on Instagram placements still work through the Page connection in phase 3, so the build continues.
4. Create the new Page. Expect a username variant; facebook.com/circadianrest is held by the old Page. Add the Page to the portfolio. Add a second Page admin.
5. Turn on **two-factor requirement for everyone** in Business settings, Security Center.
6. **Submit business verification** with the Dough Labs documents. Try email verification first, documents second. Skip domain verification for now: expect "already verified by another business" and do not burn an appeal on it.
7. **Add UpClick as a partner** by UpClick's portfolio ID and assign the Page with the permissions Sam needs. Under option A this step is reversed: the Dough Labs person is the partner.
8. Do not create the ad account yet.

### Phase 3. Move the Instagram (Jacob, from his phone, 15 minutes)

1. Instagram, Edit profile, Page. Tap the connected "Circadian Rest" Page and Disconnect. If greyed out, use Settings and activity, Business tools and controls, Connect or disconnect. Nothing about followers, content or in-app Insights changes; cross-posting to the old Page stops, which is meaningless anyway.
2. Same screen, Connect or create, Login to Facebook with the account that admins the new Page, pick the new Page, Connect. **Decline any prompt to add that Facebook account to Accounts Center.**
3. Reconnect Metricool if it was connected by Facebook login.
4. Stop condition: if the disconnect fails against the unavailable Page, do not use the "switch to personal and back" workaround yet. It clears the link in practice but loses Insights history and pauses promotions. Park it behind the phase 5 support case.

### Phase 4. Ads and Shopify (Sam, once verification is in and the Page is connected)

1. Create the ad account inside the portfolio. Currency USD, timezone set once and forever. Verify the phone number on the Account Overview page before the first ad ("you now need to verify a phone number before you can run ads").
2. Add the new card. Set the account spending limit. Expect the ad account limit of one "until they make a confirmed payment" and a Meta-set daily spending limit in the tens of dollars that rises on its own.
3. Run the $5 test ad from the new Page to Instagram and Facebook placements. Expect a possible identity or payment "unusual activity" hold on a brand-new portfolio; it clears with the verification button in Business Support Home, usually within 48 hours.
4. **Shopify.** The connecting person must have full control of the portfolio and Page and be a staff member on the store. Remove the old Facebook & Instagram channel if it is still installed, open a private window logged into only the new Facebook account, install the channel, connect the portfolio, Page, new pixel, Instagram, and choose Maximum data sharing (pixel plus Conversions API). If Shopify reports "each asset is already associated with a different shop", that is the dead connection and it needs Shopify Support, not Meta.
5. Strip the old pixel 1971038363401583 from the theme: search theme.liquid for the fbq block, check Customer events and Online Store preferences, confirm with Meta Pixel Helper.
6. Scale on the agreed curve: small, prove the retargeting signal, 20 to 30 percent a week.

### Phase 5. Parallel recovery track (Jacob's decision, does not block the build)

Purpose: release the Instagram claim, the domain claim and the Page username if they turn out to be held by the dead portfolio, and recover 18 months of pixel data if it still exists. None of this is worth waiting for.

Ranked by realistic odds, none high:

1. **Small claims against Meta Platforms, Inc. in DC Superior Court.** Meta's Commercial Terms permit "an individualized action in small claims court" and the 30-day Notice of Dispute window has already run. This is the only channel with documented account restorations (Engadget, June 2024: three of five plaintiffs got at least one account back; one had a reset link arrive half an hour before the hearing). Plead for restoration of portfolio 921971839686539, ad account 633704592556946 and the Page as the settlement term, with damages secondary. Cost: filing fee and Jacob's time. Meta's counsel tends to call before the hearing.
2. **Meta Verified for business on the Instagram** (roughly $15 a month at the base tier, cancel after). It is the only self-serve route to a human agent. Open a case with the six IDs and Meta's own 9 May 2025 email naming the unauthorised user, and ask for three specific things: remove the Instagram from portfolio 921971839686539, release circadianrest.com, and release the Page username. One documented caveat: Meta says enhanced support "may not be available to all subscribers at this time", and there may be a requirement to control a business portfolio, which is another reason to build first.
3. **DC Attorney General follow-up.** The case that produced the refund has a live Meta contact. Ask the paralegal to reopen it for asset restoration only, citing the March 2024 letter from 41 attorneys general demanding Meta staff up account-takeover response.
4. **AAA arbitration under the Commercial Terms** if small claims is dismissed. Meta pays the fees for claims under $75,000.
5. Everything already tried (BBB, FTC, other AGs, paid reinstatement firms, Pro Team) stays closed.

## 7. Do-not list

- Do not create another Facebook account for anyone involved.
- Do not add any Facebook login to the Instagram's Accounts Center.
- Do not put the fraud-affected card on any Meta surface.
- Do not verify the domain until the human-support track has had a go at releasing it.
- Do not make Sam the sole admin of anything Dough Labs is meant to own.
- Do not chargeback the old charges (they were refunded anyway) and do not try to log in to the disabled account: each attempt is a fresh signal tying the identity to a removed account.
- Do not call any "Meta support" phone number. Meta publishes none.

## 8. Questions for Jacob before the build

1. Is there a second real person at Dough Labs LLC (co-owner, spouse, employee) with a Facebook account that is several years old, in their real name, never restricted, with 2FA on? This one answer decides the structure.
2. If not, will he use his personal account to create the portfolio and add a second admin the same day, now that the June 2026 disable is explained as ban evasion rather than duplicate-account enforcement?
3. Does anyone at Dough Labs control DNS for circadianrest.com and an @circadianrest.com mailbox other than jacob@?
4. Was the circadianrest.com domain verified in the old Business Manager, and was the Instagram added to it via login (claimed) or only through the Page? His screenshots may show Business settings pages that answer both.
5. In Metricool, is the Instagram connected by Instagram login or by Facebook login?
6. Is he willing to run the small-claims track in parallel? It is his time and name.

## 9. Sources to verify before sending (Meta pages, quoted from search excerpts)

- Terms of Service, one account: https://www.facebook.com/terms
- Authentic Identity Representation: https://transparency.meta.com/policies/community-standards/authentic-identity-representation/
- Account Integrity (ban evasion, "common ownership"): https://transparency.meta.com/policies/community-standards/account-integrity/
- Suspended or disabled account, 180 days: https://www.facebook.com/help/103873106370583
- How Meta uses facial recognition to verify you: https://www.meta.com/help/policies/3701579170107659/
- Create a business portfolio: https://www.facebook.com/business/help/1710077379203657
- Verify your business: https://www.facebook.com/business/help/2058515294227817
- Why your business can't be verified (authorisation ground): https://www.facebook.com/business/help/2342133782492969
- Domain verification: https://www.facebook.com/business/help/321167023127050
- Ad account permanently in portfolio: https://www.facebook.com/business/help/915885887059947
- Add partners: https://www.facebook.com/business/help/708679622611131
- Give a partner access: https://www.facebook.com/business/help/1717412048538897
- About advertising restrictions: https://www.facebook.com/business/help/975570072950669
- Troubleshoot a disabled or restricted account: https://www.facebook.com/business/help/422289316306981
- About Business Support Home: https://www.facebook.com/business/help/254088759757736
- Ad account limit until confirmed payment: https://www.facebook.com/business/help/443041549525801
- Phone verification before first ad: https://www.facebook.com/business/help/1064155054687612
- Daily spending limits set by Meta: https://www.facebook.com/business/help/563129151097553
- Instagram can be owned by one business: https://www.facebook.com/business/help/1125825714110549
- Add or change the Page connected to Instagram: https://help.instagram.com/570895513091465
- Boost an Instagram post without a Meta ad account: https://www.facebook.com/business/help/630632987544366
- Meta Verified for businesses: https://help.instagram.com/979477020028617 and https://www.facebook.com/business/help/832027668252804
- Recover a hacked or compromised business portfolio: https://www.facebook.com/business/help/25302697499431030
- Commercial Terms (arbitration, small claims): https://www.facebook.com/legal/commercial_terms
- Self-Serve Ad Terms: https://www.facebook.com/legal/self_service_ads_terms
- Shopify channel requirements: https://help.shopify.com/en/manual/online-sales-channels/facebook-instagram-by-meta/requirements-and-considerations
- Engadget on small claims outcomes: https://www.engadget.com/how-small-claims-court-became-metas-customer-service-hotline-160224479.html
- 41 attorneys general letter, March 2024: https://www.naag.org/policy-letter/41-attorneys-general-call-on-meta-to-protect-users-accounts-from-scammers/
- Meta on Ducktail and NodeStealer malware: https://about.fb.com/news/2023/05/how-meta-protects-businesses-from-malware/

Not found in Meta's documentation despite searching, and therefore treated as unknown: whether restrictions propagate from a client portfolio to its admin's other portfolios; whether verifying an entity previously tied to a disabled portfolio triggers linkage; any Instagram-side control to remove the account from a portfolio; whether disabled portfolios are ever purged; the exact mechanism Meta uses to establish "common ownership".
