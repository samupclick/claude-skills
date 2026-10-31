# VOC thread fixtures (VOC_BACKEND=fixture)

SYNTHETIC — every thread here is invented so `scripts/pull_voc.py` can be built and tested without the
network. Names, companies, and figures inside the comments are fake on purpose: they exist to exercise the
anonymiser and its validator. One file per thread, matched to `config/clients/<slug>.json` → `voc.public_sources`
by the `url` field. Shape is ours (`url`, `title`, `comments[{id, text, score}]`, no authors); the live Reddit
backend (T13) normalises into it. Replace the placeholder URLs in the config with real threads at go-live and
switch `VOC_BACKEND=reddit`; these files then stop matching and stay as test fixtures.
