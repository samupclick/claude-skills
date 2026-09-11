# Trades Movement Data for Robot Training: Landscape and Feasibility

*Research run completed 11 September 2026. Method: four parallel web-research sweeps (about 200 searches) covering (1) companies collecting human demonstration data for robots, (2) trades and construction robotics plus capture hardware, (3) data economics, investors and law, (4) the technical evidence that egocentric human video actually trains robots. Most publisher pages were blocked at the network level, so figures come from search-engine summaries of the cited pages; anything marked "unverified" should be checked against the linked source before it goes in front of an investor.*

---

## 1. The short answer

**The idea is real, the market exists, and it is already crowded, but nobody owns the skilled-trades vertical.** In the eighteen months to September 2026, "pay people to wear a camera and record their work so robots can learn" went from research curiosity to a funded category:

- Figure launched **Index** (Aug 2026), a gig app with 44,000 weekly active recorders, 16 million videos from 108 countries, $15M paid out and a stated plan to spend over $1B on data and compute in the next year. ([Forbes](https://www.forbes.com/sites/johnkoetsier/2026/08/26/figure-launches-gig-platform-to-get-humans-to-do-work-to-train-robots-will-spend-1-billion/))
- **DoorDash Tasks** (Mar 2026) lets 8 million couriers record chores for AI and robotics customers. ([DoorDash](https://about.doordash.com/en-us/news/introducing-doordash-tasks))
- **Build AI** put custom camera glasses on 14,000+ factory workers in Southeast Asia and open-sourced roughly one million hours of first-person factory video (Apr 2026). ([Humanoids Daily](https://www.humanoidsdaily.com/news/build-ai-scales-to-100-000-hours-as-data-scaling-becomes-robotics-new-frontier))
- **Luel** (YC W26) raised a $31.2M seed for a rights-cleared marketplace with 500,000 contributors and explicitly names "first-person video paired with IMU sensor data" as the embodied-AI bottleneck. ([Luel](https://www.luel.ai/resources/blog/luel-seed-31m-general-catalyst-lightspeed))
- **XDOF** went from stealth to a reported $1.2B Series B valuation in three months on ~$50M annualised revenue selling human-demonstration and teleop data to about 20 labs. ([TechCrunch](https://techcrunch.com/2026/09/04/xdof-just-three-months-out-of-stealth-is-in-talks-for-a-series-b-at-a-1-2b-valuation/))
- Nvidia showed a **log-linear scaling law** between hours of egocentric human video and robot success, training a 22-degree-of-freedom hand "primarily from 20,000+ hours of egocentric human video with no robot in the loop." ([EgoScale](https://research.nvidia.com/labs/gear/egoscale/))

**What nobody has done:** build a pose-labelled, commercially licensed dataset of plumbers, electricians, carpenters, HVAC techs and similar trades doing real on-site work. Every program above collects household chores or generic factory and warehouse work. The closest touches are Claru (lists carpentry and repair among categories), Human Archive (a welding mention, mostly label-stripping and shoe-stitching in India), micro1 (a recruiting page aimed at electricians and plumbers), and DeepReach (places capture devices with "workshops, repair shops" partners). None is trades-focused, and none has published trades data.

**The catch:** the honest technical read is that trades work is a poor target for training today's robot *policies* directly (high force, tool use, deformable materials, confined spaces, and video carries no force signal) but a strong target for the pretraining, world-model and diversity layer that labs are paying for now. That shapes what you should build and how you should pitch it.

---

## 2. Feasibility scorecard

| Dimension | Verdict | Why |
|---|---|---|
| Market demand | **Strong** | Figure, Nvidia, Skild, Physical Intelligence, Generalist, Dyna, 1X, Tesla and Sunday all train on human egocentric data in 2026; investors put $47B into physical AI in H1 2026. |
| Trades white space | **Open** | No company found whose core business is trades or construction egocentric data; all public trades-adjacent datasets (Ego4D occupational slices, Ego-Exo4D, Assembly101, EPIC) are non-commercial. |
| Technical usefulness of the data | **Conditional** | Useful only if it carries 3D hand pose plus 6-DoF camera pose and task labels. Plain phone video or watch accelerometer alone is close to worthless to labs as action data. |
| Fit to current robots | **Weak today, improving** | Reported gains are on tabletop, low-force household tasks. Fastening, cutting, torquing and sealing need force or tactile channels that glasses cannot capture. |
| Unit economics | **Thin at commodity prices, workable at specialist prices** | Bulk egocentric footage reportedly trades at $2–5 per hour; QA-passed raw capture at $15–22 per hour; annotated with hand pose at $30–40 per hour; Chinese robot-data training grounds quote $70–140 per hour. Tradesperson wages are $30–37 per hour in the US and Australia. |
| Legal exposure | **High but manageable** | Customer homes (bathrooms especially), all-party audio consent states, UK GDPR data-protection impact assessments, Australian state surveillance acts, unionised sites. |
| Competitive threat | **High** | Labs are vertically integrating collection (Figure Index, Sunday gloves, Generalist handhelds, Build AI glasses). Well-funded generalist vendors could add a "trades" category in a quarter. |
| Bootstrap path | **Real** | The Build AI precedent: an 18-year-old built his own glasses, open-sourced 10,000 hours, then raised $5M and then ~$15M. DeepReach will hand devices to a local partner who runs collection as their own business. |

**Overall: feasible as a focused vertical data business or as the trades supplier into an existing marketplace, not as a new general-purpose platform.** The asset you can build that the incumbents cannot easily copy is a trusted network of licensed tradespeople and site-owners who consent to recording, plus the domain knowledge to label what matters.

---

## 3. Who is pursuing this (September 2026)

The market has three layers. The names in bold are the ones that matter most for your positioning.

### 3a. Robot and model companies running their own human-data operations

| Company | Program | Hardware | Recorders and pay | Scale | Segment | Source |
|---|---|---|---|---|---|---|
| **Figure AI** | Index app (Aug 2026); Project Go-Big with Brookfield (100k+ apartments) | Shipped recording device; head-mounted | Crowd; "paid by the minute"; $15M paid so far | 16M videos, 108 countries, 44k WAU; $1B committed | Household and workplace | [Forbes](https://www.forbes.com/sites/johnkoetsier/2026/08/26/figure-launches-gig-platform-to-get-humans-to-do-work-to-train-robots-will-spend-1-billion/), [Figure](https://www.figure.ai/news/project-go-big) |
| **Tesla Optimus** | Data Collection Operators; switched from mocap suits to camera-only mid-2025 | Helmet with five cameras plus backpack up to 40 lb | Employees, up to $48/hr in Palo Alto | Hundreds per shift | Factory kitting, household | [Fortune](https://www.fortune.com/2024/08/19/tesla-robot-hiring-workers-optimus-training-ai), [Sherwood](https://sherwood.news/tech/teslas-robots-get-the-same-treatment-as-its-cars-video-training/) |
| **Sunday Robotics** | "Memory Developers" wear a $200 Skill Capture Glove at home | Glove matched to the Memo robot hand | Home users; pay undisclosed | 2,000+ gloves, 500+ homes, ~10M episodes; $165M Series B at $1.15B | Household | [Humanoids Daily](https://www.humanoidsdaily.com/news/sunday-unveils-memo-a-wheeled-domestic-robot-that-learns-from-200-gloves) |
| **Generalist AI** | UMI-style handheld "data hands" in homes, warehouses, workplaces | Handheld gripper with camera | In-house and contract; undisclosed | 270k hours (Nov 2025) to 500k+ (mid-2026); $400M Series B at $2B | Household, warehouse | [Robot Report](https://www.therobotreport.com/generalist-raises-400m-to-scale-its-general-purpose-ai-models/) |
| **Dyna Robotics** | DYNA-2 trained on 1M+ hours of human egocentric video (Aug 2026) | Not disclosed | Not disclosed | $143.5M raised | Household, commercial | [PR Newswire](https://www.prnewswire.com/news-releases/dyna-robotics-unveils-dyna-2-world-action-model-demonstrating-first-true-scaling-law-in-robotics-powered-entirely-by-human-data-302847114.html) |
| **Skild AI** | S1 learns a task from one human video; scaled 1k to 100k hours; "$3 on QC for every $1 on collection" | Headcam plus YouTube | Not disclosed | ~$1.4B round Jan 2026 | General | [Skild](https://skild.ai/blogs/s1) |
| **Nvidia** | EgoScale (20,854 hrs across manufacturing, retail, healthcare, home) behind GR00T N1.7; DreamDojo world model on 44,711 hrs | Mixed | Public datasets plus partners | 20k–45k hours | Multi-industry | [EgoScale](https://research.nvidia.com/labs/gear/egoscale/), [DreamDojo](https://github.com/NVIDIA/DreamDojo) |
| Physical Intelligence | Co-trains pi0.5 / pi0.7 on egocentric human video with hand poses as actions; fine-tuning on human video "doubled performance on depicted tasks" | Wearable cameras | Not disclosed | Undisclosed | General | [PI on X](https://x.com/physical_int/status/2001096200456692114), [pi0.7](https://www.pi.website/download/pi07.pdf) |
| 1X | World model with ~900 hrs egocentric human video "mid-training" | Not disclosed | In-house | 900 hours | Household | [1X](https://www.1x.tech/discover/1x-world-model-lab) |
| Mimic Robotics | U1 wearable exoskeleton matched to its M1 hand; captures from factory workers in live production | Exoskeleton | Factory workers | $16M seed | Industrial | [SiliconANGLE](https://siliconangle.com/2025/11/04/mimic-raises-16m-build-ai-models-human-like-robotic-hands/) |
| Boston Dynamics / TRI, BMW, Hyundai | Xsens suits and Manus gloves on factory workers | IMU suit and gloves | Employees | Undisclosed | Automotive assembly | [Xsens](https://www.xsens.com/resources/bmw-group-uses-xsens-motion-capture-to-support-humanoid-robot-training) |
| AgiBot, UBTech (China) | Dedicated data-collection centers; instructors do up to 600 reps a day | Handheld and VR | Employees, ¥20–40/hr (~$3–6) | 1M+ episodes (AgiBot World) | Handling, sorting | [KrASIA](https://kr-asia.com/inside-agibots-shanghai-center-robots-learn-to-master-tasks-in-human-like-ways), [Rest of World](https://restofworld.org/2026/china-robots-training-centers-workers/) |

### 3b. Pure-play data suppliers

| Company | What they collect | Hardware | Who records and pay | Funding | Trades relevance | Source |
|---|---|---|---|---|---|---|
| **XDOF** (Berkeley, 2024) | Teleop plus egocentric operators with body sensors; folding, box flattening | Body sensors | Trained collector teams worldwide | $70M Series A; Series B talks at $1.2B; ~$50M ARR; 20 lab customers | None | [TechCrunch](https://techcrunch.com/2026/09/04/xdof-just-three-months-out-of-stealth-is-in-talks-for-a-series-b-at-a-1-2b-valuation/) |
| **Build AI** (2025) | Egocentric factory video; Egocentric-1M open under permissive license | Custom head-mounted glasses, RGB only | Factory workers via SE Asia factory networks | ~$15M (Abstract, Pear, HF0) | Industrial, not trades | [Humanoids Daily](https://www.humanoidsdaily.com/news/build-ai-scales-to-100-000-hours-as-data-scaling-becomes-robotics-new-frontier) |
| **Luel** (YC W26) | Rights-cleared multimodal marketplace; egocentric campaigns include gemstone carving, cooking, warehouse; video paired with IMU | Contributor devices | 500k contributors, 96 countries | $31.2M seed (General Catalyst, Lightspeed); $2M ARR weeks after demo day | Campaign-based; could host a trades campaign | [Luel](https://www.luel.ai/resources/blog/luel-seed-31m-general-catalyst-lightspeed) |
| **Human Archive** (YC) | Camera caps on Indian service and factory workers: label stripping, shoe stitching, welding, sorting; building tactile gloves, mocap suits, wrist cams | Camera caps, RGB-D | Gig workers, $1/hr base (reported $2.62/hr); consent under regulatory review; Urban Company and Pronto declined to partner | $8.2M seed (Wing, NVP, YC) | Home services partners; welding | [TechCrunch](https://techcrunch.com/2026/05/26/human-archive-taps-into-indias-services-startups-to-collect-data-for-physical-ai/) |
| **DeepReach** (YC) | Places stereo wearable capture devices with local "data partners" who run collection as their own business in warehouses, workshops, farms, kitchens, repair shops | Stereo wearable | 475 devices, 100+ partners, 7 countries; target 10,000 devices | YC | **Closest model to "tradesperson as data partner"** | [YC](https://www.ycombinator.com/companies/deepreach-inc) |
| **micro1** (Palo Alto) | Egocentric chores; also markets to skilled-trade workers: electricians record wiring, panel work, safety checks; plumbers film fixture replacement and diagnostics | iPhone strapped to head | Thousands of contractors, 50+ countries; $15/hr (Nigeria), $80 per 2 hrs (LA) | Undisclosed | Has a trades recruiting page; no trades dataset published | [micro1](https://www.micro1.ai/experts-guide/how-skilled-trade-based-workers-can-earn-from-ai-training), [MIT TR](https://www.technologyreview.com/2026/04/01/1134863/humanoid-data-training-gig-economy-2026-breakthrough-technology/) |
| **Claru** | Egocentric capture across countries; workplace categories include carpentry, tailoring, screen printing, phone and tool repair | GoPro, DJI, smartphones | Gig and workplace workers; per-project pricing | Undisclosed | Lists carpentry; not focused | [Claru](https://claru.ai/solutions/egocentric-video-data) |
| **Cortex AI** (YC, 2025) | Real-workplace egocentric video with per-frame hand and body pose, depth, subtask labels; robot trajectories; marketplace where workplaces are paid to host sessions | Not disclosed | Via industry partners | $6.5M seed | Workplace, industrial | [Cortex](https://cortexrobot.ai/), [YC](https://www.ycombinator.com/companies/cortex-ai) |
| Microagi (Munich) | Factory plus household; ran free apartment cleanings to collect data; exclusive licensing | Not disclosed | Own operators | $55M seed (Germany's largest) | Factory | [Sifted](https://sifted.eu/articles/munich-robotics-startup-microagi-raises-55m-germanys-largest-ever-seed-round) |
| Ropedia | HOMIE head-mounted wearable | HOMIE | Not disclosed | $22M round, $30M total | Unknown | [Robot Report](https://www.therobotreport.com/ropedia-raises-22m-scale-data-collection-training-robots/) |
| Vision Lab (YC) | Industrial data from 2,000+ partner factories | Unspecified | Factory workers | $6M seed | Industrial | [Vision Lab](https://thevisionlab.ai/articles/seed-2026) |
| Encord | Egocentric from factories; San Leandro lab; UMI | Rigs, UMI | Operators | €50M Series C (Feb 2026) | Factory | [TNW](https://thenextweb.com/news/encord-raises-e50m-to-build-the-data-layer-for-physical-ai) |
| Scale AI | Physical AI data engine; 100k+ production hours; contractors record POV demos at $15–60/hr | Leader-follower arms, headcams | Contractors | Meta-backed | Lab and industrial manipulation | [Scale](https://scale.com/blog/physical-ai) |
| Objectways, Egolab, Sunain, Instawork, Mecka, Shaip, Unidata, Labellerr, truelabel, Keymakr, Digital Divide Data | Egocentric collection as a service; Unidata sells a 4,050-hour set on Databricks; Sunain mails wrist cameras to 1,400 LA contributors | Various | $3/hr (India) to $80 per 2 hrs (LA); Egolab faced no-consent, no-pay allegations | Small | Mixed household and textile | [TechSpot](https://www.techspot.com/news/111686-gig-workers-getting-paid-film-their-daily-chores.html), [Scroll.in](https://scroll.in/article/1092960/how-big-tech-is-harnessing-the-data-of-indian-factory-workers-to-train-robots) |

### 3c. Marketplaces, licensors and crypto networks

| Company | Model | Pay to contributors | Relevance | Source |
|---|---|---|---|---|
| **DoorDash Tasks** | 8M couriers record chores for AI and robotics customers | Up to ~$25/hr claimed; a Wired reporter earned negligible pay in a week | Distribution scale nobody can match | [DoorDash](https://about.doordash.com/en-us/news/introducing-doordash-tasks), [Bloomberg](https://www.bloomberg.com/news/articles/2026-03-19/doordash-s-new-paid-tasks-turn-couriers-into-ai-and-robot-trainers) |
| **Mercor** | Expert marketplace; "host robotics data collection at your business" program; licenses footage to robotics companies | $25–250/hr for experts generally | Only mechanism found that could route through trade shops | [Mercor](https://www.mercor.com/resources/experts/economics/) |
| Troveo | Rights-cleared video licensing; 8M+ hours; sells "step-by-step demonstrations of physical tasks, exo- and egocentric" | $0.75–3 per minute to owners; $20M+ paid out; markets "up to $1,000/hr" | Pricing comparable | [Troveo](https://www.troveo.ai/datasets), [BusinessWire](https://www.businesswire.com/news/home/20260428319383/en/Troveo-Accelerates-AI-Model-Development-Expands-AI-Training-Data-Platform-to-Five-New-Categories-Announces-$20-Million-in-Payouts) |
| Protege, Wirestock | Video licensing | $1–4 per minute; Wirestock $23M Series A | Comparable | [AI Optimist](https://www.theaioptimist.com/p/the-5m-ai-video-licensing-wave-why) |
| BitRobot / FrodoBots SeeSaw, PrismaX, Sapien | Token-rewarded egocentric and teleop networks; RoboCap $1,000 six-camera wearable | Tokens and points | Crypto-incentive model | [BitRobot](https://bitrobot.ai/blog/introducing-sn-05-seesaw-by-virtuals) |

### 3d. Trades and construction robotics (the eventual customers)

Construction robotics in 2026 is dominated by single-task machines that learn from their own fleet data or from BIM and CAD, not from human motion: Canvas (acquired by JLG, Jan 2026), Okibo, Dusty, Monumental ($32M Series B, 150+ bricklaying robots), FBR, Hilti Jaibot, DEWALT's drilling robot for data centers, Renovate Robotics' roofing gantry. **Bedrock Robotics** ($270M Series B, first operator-less excavator deployments Aug 2026) is the clearest case of learning from human operators, using "tens of thousands of hours in the field." Welding is the only trade with mature data-driven learning (Path Robotics' Obsidian model on "tens of millions of welded inches"; Novarc; Persona AI and Neura humanoid welding pilots at HD Hyundai shipyards). **No "robot electrician" or "robot plumber" startup was found.** Sources: [JLG](https://www.jlg.com/en/press-releases/jlg-advances-job-site-of-the-future-vision-through-canvas-acquisition), [Tech.eu](https://tech.eu/2026/07/15/monumental-secures-32m-series-b-to-accelerate-construction-automation/), [Construction Dive](https://www.constructiondive.com/news/bedrock-robotics-raise-ai-automation-funding/811982/), [Path](https://www.automate.org/ai/industry-insights/path-robotics-brings-physical-ai-to-welding), [Humanoids Daily](https://www.humanoidsdaily.com/news/from-prototype-to-production-persona-ai-and-hd-hyundai-solidify-humanoid-welding-partnership).

Labor context: US construction needs 349,000 new workers in 2026; Randstad reports HVAC demand up 67% and electricians up 18% since 2022; BlackRock committed $100M to trades training in March 2026. ([Fortune](https://fortune.com/2026/03/20/skilled-trade-demand-randstand-report-electricans-technicans-construction-workers-six-figure-salaries-data-center-boom/), [Fortune](https://fortune.com/2026/03/11/blackrock-skilled-trade-worker-training-investment-100-million-dollars-electricans-plumbers-hvac-technicals-six-figure-salaries-stable-jobs-gen-z-larry-fink))

---

## 4. Does the data actually work? What labs want

### 4a. Evidence that human video trains robots

The pattern across every result with real robot-side gains is the same: **egocentric RGB plus 3D hand pose plus 6-DoF camera pose, with task labels.**

- **EgoScale** (Nvidia, Feb 2026): 20,854 hours of action-labelled human video; log-linear scaling law; +54% average success on a 22-DoF hand. ([arXiv](https://arxiv.org/abs/2602.16710))
- **EgoZero** (NYU, 2025): Aria glasses only, zero robot data, 20 minutes of human data per task, 70% zero-shot success on seven tasks. ([arXiv](https://arxiv.org/abs/2505.20290))
- **EgoDex** (Apple, 2025): 829 hours, 338k demos, 68-joint hand skeleton, 194 tabletop tasks. Non-commercial license. ([Apple](https://machinelearning.apple.com/research/egodex-learning-dexterous-manipulation))
- **H-RDT** (Tsinghua, AAAI 2026): pretraining on hand-pose human video gave +40.5% real-world improvement and beat pi0. ([arXiv](https://arxiv.org/abs/2507.23523))
- **Physical Intelligence** (Dec 2025): fine-tuning pi0.5 on human video doubled performance on the tasks depicted. ([X](https://x.com/physical_int/status/2001096200456692114))
- **HumanScale** (2026) claims egocentric human video can outperform real-robot data for pretraining. ([arXiv](https://arxiv.org/abs/2606.20521))
- **Diversity beats hours**: Lin et al. (ICLR 2025) found generalization follows a power law in the number of environments and objects, and extra demonstrations per environment have minimal effect past a threshold. ([arXiv](https://arxiv.org/abs/2410.18647))

Video **without** pose still has value through latent-action methods (LAPA, UniVLA) and world models (DreamDojo, 1X), but it slots into the bottom of Nvidia's "data pyramid" and competes with free internet video.

### 4b. What this means for a phone-and-watch rig

| Channel | Value to a lab | Notes |
|---|---|---|
| Egocentric RGB, wide field of view, 30 fps, hands in frame | Essential | Every pipeline uses it |
| 6-DoF camera pose (SLAM or ARKit) | Essential | Needed to express hand motion in a stable frame |
| 3D hand keypoints, both hands, with confidence | Essential | This is the "action" label; Aria, Vision Pro and Quest track it on-device; phone needs post-hoc estimation, which is noisier and some estimators (WiLoR, HaMeR) are non-commercial |
| Task label plus sub-step timestamps | Essential | Cheapest to add: narrate what you're doing |
| Site, tools, materials, hazards metadata | High | Supports the diversity accounting labs care about |
| Depth or point cloud | Useful, optional | iPhone LiDAR gives 256x192 |
| Audio | Useful | Tool sounds and narration |
| Wrist accelerometer (smartwatch) | Auxiliary only | **No robot-learning pipeline found uses standalone IMU as an action signal.** Double-integrated position drifts in seconds and carries no finger state. Useful for activity segmentation and timestamps only. |
| Force or tactile | Highly valuable for trades, absent from glasses | Needs instrumented gloves or tools (DexUMI, ForceMimic-style handheld force sensors) |

So the smartwatch idea is a nice-to-have, not the product. The phone is viable **only** if you use it as a head-mounted ARKit rig that logs pose, depth and IMU in sync (apps such as Stray Scanner or Record3D do this; the 2026 MobileEgo Anywhere paper documents exactly this protocol), and you add hand pose. Consumer Meta glasses are ergonomically perfect for a jobsite and useless for this purpose: three-minute clip cap, no pose, no depth, no raw IMU.

### 4c. Why trades are hard for robots, and why that cuts both ways

Fastening, cutting, torquing fittings, pulling cable, running sealant and working inside walls and crawlspaces are high-force, bimanual, long-horizon, deformable-material tasks in confined spaces. Force-aware models show large gains over vision-only on exactly these contact-rich tasks (ForceVLA +23%, tactile-plus-wrench +80% in clutter extraction), and none of that signal is in a video. Google's Gemini Robotics 1.5 paper notes its motion-transfer method weakens as the embodiment gap grows. Current humanoid and bimanual research platforms cannot swing a hammer or torque a union.

That is the bad news for "robots doing plumbing in 2028." The good news for a dataset business: it makes trades video a **scarce, high-diversity, uncontested slice** that labs need for pretraining, planning, world models and evaluation now, and for policy training when hardware catches up. Physical Intelligence's finding that human video helps most "on tasks depicted in the human videos" is the strongest argument for a targeted vertical dataset over more household hours.

---

## 5. Economics

### 5a. What buyers pay and what recorders earn

| Item | Figure | Source |
|---|---|---|
| Bulk undifferentiated egocentric footage | $2–5 per hour (single blog source) | [Flikforge](https://flikforge.com/robot-data-glut-egocentric-video-physical-ai/) |
| QA-passed raw egocentric capture | $15–22 per hour | [Claru](https://claru.ai/blog/best-egocentric-data-providers) |
| Annotated with hand pose and object tracks | $30–40 per hour; dense annotation toward $60 | [DataX Power](https://www.dataxpower.com/blog/humanoid-robot-data-collection-cost) |
| Full humanoid teleop programs | $80–150 per hour | same |
| Chinese government-backed training grounds, sale price | ¥500–1,000 per hour (~$70–140) | [Rest of World](https://restofworld.org/2026/china-ai-robotics-training-data/) |
| General licensed video (Troveo, Protege, Wirestock) | $1–4 per minute ($60–240 per hour); Troveo markets "up to $1,000/hr" | [AI Optimist](https://www.theaioptimist.com/p/the-5m-ai-video-licensing-wave-why) |
| Tesla data collection operator | $25–48 per hour, employee | [Fortune](https://www.fortune.com/2024/08/19/tesla-robot-hiring-workers-optimus-training-ai) |
| Figure operator and data creator roles | $25–36 per hour | [BuiltIn](https://builtin.com/job/humanoid-robot-operator/3321165) |
| Gig recorders (micro1, Instawork) | $15/hr Nigeria; ~$40/hr LA ($80 per 2 hrs usable) | [MIT TR](https://www.technologyreview.com/2026/04/01/1134863/humanoid-data-training-gig-economy-2026-breakthrough-technology/) |
| Offshore gig (Human Archive, Objectways) | $1–3 per hour | [TechCrunch](https://techcrunch.com/2026/05/26/human-archive-taps-into-indias-services-startups-to-collect-data-for-physical-ai/) |
| US electrician / plumber / carpenter median wage | $34.37 / $30.27 / $31.55 per hour | [BLS via SkilledTradesIQ](https://skilledtradesiq.com/salaries/bls-2025-oews-release/) |
| UK electrician / plumber | ~£20 / £19 per hour employee | [PayPrecision](https://payprecision.co.uk/salaries/electrician/) |
| Australia electrician / plumber | A$37 / A$34 per hour employee; A$85–175 charge-out | [PayScale AU](https://www.payscale.com/research/AU/Job=Electrician/Hourly_Rate) |
| Skild's QC ratio | $3 of quality control for every $1 of collection | [Skild](https://skild.ai/blogs/s1) |
| Typical QA rejection | 20–30% of episodes | [Dexset](https://dexset.ai/blogs/teleoperation-data-collection-robot-learning-complete-2026/) |

No vendor publishes a flat rate and no price exists for skilled-trade egocentric data specifically. Everything is quoted per project, driven by capture complexity, annotation depth, exclusivity and rights.

### 5b. Unit economics, two scenarios

Assumptions: a tradesperson records 5 usable hours per working day; 25% QA rejection; you pay the recorder a passive stipend on top of their normal wage because the recording costs them hassle, not time; you spend roughly one hour of labelling and QA per recorded hour at $20 per hour (offshore or tooling-assisted).

| Per recorded hour | Commodity positioning | Specialist positioning |
|---|---|---|
| Sale price | $20 | $90 |
| Net of 25% rejection | $15 | $67.50 |
| Stipend to tradesperson | $8 | $20 |
| Labelling and QA | $10 | $20 |
| Hardware, storage, consent admin (amortised) | $3 | $5 |
| **Gross margin per hour** | **negative $6** | **$22.50** |
| Recorder earns per week (25 hrs) | $200 | $500 |

Commodity pricing does not work in a high-wage country; that is why the volume players use Indian, Nigerian and Southeast Asian labor. The business only works if the trades slice commands the specialist price, which the Chinese training-ground and Troveo comparables suggest is plausible for pose-labelled, rights-cleared, hard-domain data, but which no buyer has yet confirmed publicly. **Getting one lab to state a price for trades data is the single most important early milestone.**

### 5c. Investor climate

- Physical AI took $47.4B across 521 deals in H1 2026, but "bigger rounds, not more companies." ([Value Add Pulse](https://valueaddvc.com/pulse/physical-ai-funding-47-billion-h1-2026-data))
- The entire disclosed data-vendor layer (~$730M) has raised less than Skild's single January 2026 round. ([Teahose](https://www.teahose.com/guides/robotics-training-data))
- Seed appetite for human-data-for-robots is real: Human Archive $8.2M, Cortex $6.5M, Mecka $8M, Build AI $5M then ~$15M, Ropedia $22M, Luel $31.2M, Microagi $55M, all in the last 12 months.
- a16z's $1.1B Machine Age Fund essay says "data, not compute, is now the binding constraint in robot learning," and in the same essay warns that if simulation takes over, "the cost curve collapses… simulation scales with compute, not with human labor." ([a16z](https://a16z.com/frontier-systems-for-the-physical-world/))
- Skepticism to price in: Ken Goldberg's "100,000-year data gap" piece argues YouTube-style footage "fails to convey the granular details necessary for producing effective robotic motion." ([Science Robotics](https://www.science.org/doi/10.1126/scirobotics.aea7390))

Precedent for bootstrapping: Build AI's founder built his own glasses, open-sourced 10,000 hours, and raised on that. Sunday shipped gloves to 500 homes before its Series B. Investors in the comparables funded **networks and transfer results**, not single-person datasets, so your concept dataset has to demonstrate a repeatable pipeline and a queue of tradespeople, not just hours.

---

## 6. Legal and privacy

| Jurisdiction | Rule | What it means on site | Source |
|---|---|---|---|
| US audio | Eleven all-party-consent states (CA, CT, FL, IL, MD, MA, MT, NV, NH, PA, WA) | Video-only or signed consent from everyone in earshot | [Recording Law](https://www.recordinglaw.com/party-two-party-consent-states/) |
| US video | No recording where there is a reasonable expectation of privacy (bathrooms, bedrooms) | A plumber's bathroom job is the riskiest category; written homeowner consent, no bystanders | [Backstreet Surveillance](https://www.backstreet-surveillance.com/blog/post/is-it-legal-to-record-audio-with-security-cameras-in-the-us) |
| US union sites | Surveillance is a mandatory subject of bargaining under the NLRA | Recording on unionised commercial sites needs bargaining or permission | [Recording Law](https://www.recordinglaw.com/us-laws/surveillance-camera-laws/workplace-surveillance-camera-laws/) |
| US biometrics | Illinois BIPA and similar statutes cover face data | Blur faces; avoid identifiable bystanders in IL | not researched further |
| UK | ICO worker-monitoring and body-worn-video guidance: DPIA, proportionality, privacy notices, retention policy under UK GDPR | Continuous body-worn video in a customer's home is high-risk processing; notice per visit | [ICO](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/cctv-and-video-surveillance/guidance-on-video-surveillance-including-cctv/additional-considerations-for-technologies-other-than-cctv/body-worn-video-bwv/) |
| Australia | State surveillance device acts; NSW Workplace Surveillance Act requires 14 days' written notice to employees; audio needs express consent of all parties | Video-only default, explicit customer consent, per-state review | [NSW SDA 2007](https://legislation.nsw.gov.au/view/whole/html/inforce/current/act-2007-064) |
| India (relevant if you outsource) | MeitY reviewing Human Archive's consent under the DPDP Act; Egolab accused of unpaid, unconsented factory recording | Buyers are starting to screen vendors for consent hygiene; a clean-consent story is a selling point | [TechCrunch](https://techcrunch.com/2026/05/26/human-archive-taps-into-indias-services-startups-to-collect-data-for-physical-ai/), [The Wire](https://m.thewire.in/article/labour/told-to-train-ai-models-indian-workers-fought-back/amp) |

Practical defaults: record on commercial and new-construction sites first (fewer bystanders, one general contractor to consent); use a per-job customer consent form for residential; blur faces, plates and screens with the same tooling Ego4D used (brighter.ai, Secure Redact); keep audio to the wearer's narration where possible; if employed rather than self-employed, get employer sign-off because the work product may be theirs. Trade-method IP is an open question with no precedent found; treat your own techniques as licensable know-how and get written releases from any other tradesperson you record.

---

## 7. What the business would look like

### 7a. Positioning

Do not build another general egocentric marketplace; Figure, Luel, DoorDash and Scale have already won that on distribution. Build **the trades vertical**: a network of licensed tradespeople and consenting sites, a capture protocol designed around trade tasks, and labels only a tradesperson can write (why this fitting, what torque, what failure modes, what code requirement). Sell it two ways: (1) as a licensed dataset slice to labs and to the construction-robotics companies in section 3d, and (2) as a managed collection service that a Luel, Cortex, Mercor or DeepReach can plug into as their trades supplier.

### 7b. The concept dataset spec (what to record so a lab takes the call)

- **Hardware, tier 0 (about $0–25 incremental):** iPhone 12 Pro or newer on a head strap running Stray Scanner or Record3D, logging synced RGB at 1920x1440 30 fps, LiDAR depth, IMU and ARKit 6-DoF pose. Apple Watch app using CMBatchedSensorManager inside a workout session for 800 Hz wrist accelerometer (segmentation channel). Audio on for narration.
- **Tier 1 (about $500–700):** add a chest- or wrist-mounted GoPro HERO13 for a hand-centric second view with GPMF IMU, the way UMI does it.
- **Tier 2 (about $700 more):** Rokoko Smartgloves ($695) for occlusion-proof finger pose on bench tasks; impractical for wet or hot work.
- **Tier 3:** apply now for Meta's Project Aria Gen 2 research kit (rolling application, free but gated). It is the only glasses form factor with on-device SLAM, hand tracking, gaze and 6–8 hour recording, and it is what EgoMimic and EgoZero used.
- **Per-episode payload:** RGB, per-frame camera pose and intrinsics, both-hands 21-keypoint pose with confidences (on-device where possible; flag frames where hands leave view), task string, ordered sub-steps with timestamps (narrate them), success or failure, trade, site ID, environment type (crawlspace, panel, wall cavity), tools and consumables, hazards, anonymised operator ID and body-size bucket.
- **Format:** LeRobot v3 (parquet plus MP4 shards with meta files), plus an HDF5 export; ship a GR00T-style modality file. Storage runs roughly 12–25 GB per hour for the phone rig, 54 GB per hour if you add a GoPro at 5.3K.
- **Pilot scale:** 50–100 hours across at least 20 sites and at least 5 task families, with 30 or more episodes per task-and-site cell. Diversity of sites and objects is what the scaling research rewards, not raw hours. Your pitch is "high-diversity, hard-domain slice," never "volume."
- **License:** commercial-use terms are your differentiator; every trades-adjacent public dataset is non-commercial.

### 7c. A 90-day plan with no capital

1. **Weeks 1–2: legal scaffolding and rig.** Draft a one-page site consent form and a recorder release; check your state or country row in section 6; set up the phone rig and test a full day of recording, upload and storage.
2. **Weeks 2–8: record the concept dataset.** Aim for 50 hours across your own jobs, prioritising commercial and new-construction sites. Narrate every sub-step. Log site, tools, materials per job.
3. **Weeks 3–8 in parallel: build the label layer.** Run on-device or open-source hand pose and camera pose over the footage; write task and sub-step labels; blur faces; export to LeRobot v3. Publish a 2–5 hour open sample on Hugging Face under a permissive license with a clear data card, the Build AI playbook.
4. **Weeks 4–10: get a price.** Apply to DeepReach's partner program, Mercor's host program, Luel campaigns, Cortex's marketplace and Figure Index as a "workplace" creator. These are simultaneously distribution, price discovery and proof that buyers exist. Cold-email the human-data leads at Physical Intelligence, Nvidia GEAR, Skild, Generalist and Dyna with the sample and the spec; ask what they would pay per hour for 1,000 hours of the same.
5. **Weeks 6–12: line up the network.** Sign five to ten tradespeople across at least three trades who will record on the same protocol for a stipend once a buyer commits. The signed queue plus the sample plus one price quote is the investor deck.
6. **Day 90: decide.** If a lab quotes at or above roughly $60 per hour for pose-labelled trades data, raise a small pre-seed and scale the network. If quotes sit at commodity levels, pivot to being the trades supplier for an existing marketplace, or to the force-and-tactile instrumented-tool angle in 7d.

### 7d. Two angles that could make it defensible

- **Instrumented tools.** Video cannot see force. A drill, torque wrench or crimper with a cheap force or torque sensor and a synced timestamp gives the one channel no glasses vendor has. DexUMI and ForceMimic show labs value it; nobody sells it for trades. This is a hardware-light way to sell something Build AI's million hours cannot.
- **Expert narration and outcome labels.** A tradesperson explaining why a joint is made a certain way, what code requires, and whether the job passed inspection is label data that gig crowds cannot produce. It maps directly onto the language conditioning every VLA uses.

---

## 8. Risks that could kill it

- **Labs stop buying.** Figure, Tesla, Sunday, Generalist and Build AI all vertically integrated collection. If the top five labs collect in-house, third-party demand comes only from second-tier labs and construction-robotics companies.
- **Simulation wins.** If synthetic data closes the gap for manipulation, the value of human-collected hours falls toward zero.
- **Someone adds "trades" as a category.** Luel or Cortex could run a trades campaign next quarter. Your defence is the licensed-tradesperson network, consent hygiene, and domain labels, not the footage.
- **Trades tasks stay out of reach for robots longer than investors' patience.** The direct policy payoff for plumbing is likely three to seven years out; position the data for pretraining and world models now.
- **A privacy incident.** One viral clip of a customer's bathroom or an unconsented apprentice ends the business. Consent-first is the product.
- **Phone-only data is rejected.** If labs insist on Aria-class pose quality, you need the research kit or a custom rig before anyone pays.

---

## 9. Recommendation

Proceed, narrowly. Record the concept dataset with the phone rig now, because it costs nothing and the market is moving monthly. But treat the smartwatch as a segmentation channel rather than a product, design the capture around hand pose, camera pose and expert labels from day one, and spend the first ninety days getting a written price from one lab rather than accumulating hours. The winning version of this company is not "the app where tradesmen film themselves." It is "the only rights-cleared, expert-labelled source of skilled-trades manipulation data, with a network of licensed tradespeople the labs cannot recruit on their own."

---

## Sources not linked inline

- Build AI Egocentric-1M announcement: https://x.com/eddybuild/status/2041751488817774968
- HyperAI on Build AI: https://hyper.ai/en/stories/f1d1921a3065a5d141416bed7278b8d8
- Human Archive funding: https://mezha.net/eng/bukvy/aac0e4fd_human_archive_raises/
- Figure Index coverage: https://www.humanoidsdaily.com/news/figure-ai-unveils-index-crowdsourcing-real-world-human-video-to-train-helix ; https://alphasignal.ai/news/figure-s-index-app-pays-44-000-people-to-train-its-humanoid-robots
- MIT Technology Review, "Humanoid data": https://www.technologyreview.com/2026/04/21/1135656/humanoid-data-robot-training-ai-artificial-intelligence/
- Washington Post interactive on chore video: https://www.washingtonpost.com/technology/interactive/2026/robot-chores-video-data/
- Zuper Glass (field-service glasses for trades, not robot training): https://www.geekwire.com/2025/seattle-startup-unveils-ai-powered-enterprise-smart-glasses-for-roofers-and-electricians/
- EgoMimic: https://arxiv.org/abs/2410.24221 ; EgoDex: https://github.com/apple/ml-egodex ; PH2D: https://arxiv.org/abs/2503.13441 ; Being-H0.5: https://arxiv.org/abs/2601.12993 ; LAPA: https://arxiv.org/abs/2410.11758 ; UniVLA: https://arxiv.org/abs/2505.06111 ; DreamDojo: https://arxiv.org/abs/2602.06949 ; GR00T N1.7: https://huggingface.co/blog/nvidia/gr00t-n1-7 ; Gemini Robotics 1.5: https://arxiv.org/abs/2510.03342 ; Phantom: https://arxiv.org/html/2503.00779v2 ; Masquerade: https://arxiv.org/pdf/2508.09976
- UMI: https://github.com/real-stanford/universal_manipulation_interface ; DexCap: https://github.com/j96w/DexCap ; DexUMI: https://github.com/real-stanford/DexUMI ; ForceMimic and force VLAs: https://github.com/OpenHelix-Team/Awesome-Force-Tactile-VLA
- MobileEgo Anywhere (phone head rig): https://arxiv.org/pdf/2605.05945 ; EgoKit: https://arxiv.org/pdf/2605.16797 ; EgoVerse: https://arxiv.org/pdf/2604.07607
- Project Aria Gen 2: https://www.projectaria.com/research-kit/ ; application: https://ai.meta.com/aria-application/
- Apple Watch high-rate IMU: https://developer.apple.com/videos/play/wwdc2023/10179/
- Meta Ray-Ban Gen 2 limits: https://www.meta.com/blog/ray-ban-meta-gen-2-now-available-ai-glasses-extended-battery-life-3k-video/ ; Oakley Meta Vanguard: https://www.uploadvr.com/oakley-meta-vanguard-glasses-official/
- Rokoko gloves: https://www.reallusion.com/iclone/motion-capture/rokoko-smartgloves.html ; Manus: https://roadtovr.com/manus-vr-gloves-quantum-order/
- LeRobot v3 format: https://github.com/huggingface/lerobot/blob/main/docs/source/lerobot-dataset-v3.mdx
- Construction worker IMU datasets (activity recognition only): https://www.nature.com/articles/s41597-022-01841-1
- Ego4D privacy and de-identification: https://ego4d-data.org/docs/privacy/
- Data licensing structures: https://www.troveo.ai/resources/ai-data-licensing ; https://www.lexology.com/library/detail.aspx?g=f23078a4-a1e7-45c9-ad93-77010e48da9f
- Sector funding: https://valueaddvc.com/pulse/physical-ai-funding-47-billion-h1-2026-data ; https://newmarketpitch.com/blogs/news/physical-ai-top-startups-fundraising
