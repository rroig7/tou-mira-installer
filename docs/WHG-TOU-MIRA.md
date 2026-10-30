# whg-tou-mira: where the voice chat add-on comes from

This installer's **BetterCrewLink-TOU + voice bridge** option installs files built and released by
a separate project, [`rroig7/whg-tou-mira`](https://github.com/rroig7/whg-tou-mira). It's usually
checked out next to this repo at `../whg-tou-mira`. This file explains that project from the
installer's side: what it is, what it publishes, and which side to change for which task.

For how the installer code handles these files (`bridge.py`, `bettercrewlink.TOU`,
`voice_update.py`), see `CLAUDE.md`.

## What whg-tou-mira is

An integration that makes BetterCrewLink proximity voice react to Town of Us: Mira role effects.
For example, jailed, blackmailed and Puppeteer-controlled players are muted, and blinded players
hear everyone muffled. It has two parts. Players need both, which is why the installer installs
them together:

| Part | What it is | Where it ends up |
|---|---|---|
| **BetterCrewLink-TOU** | A fork of BetterCrewLink (Electron app), repo `rroig7/BetterCrewLink`, branch `tou-mira` | Its own per-user app: `Programs\bettercrewlink-tou`, Uninstall `DisplayName` `BetterCrewLink-TOU …`. It doesn't replace official BetterCrewLink. |
| **Voice bridge** `TouMiraBclBridge.dll` | A client-only BepInEx plugin. It reads TOU-Mira's state in game and streams it to the app over TCP `127.0.0.1:47652` | `Among Us\BepInEx\plugins\TouMiraBclBridge.dll` |

Facts that matter here:

* **TOU-Mira itself is never modified.** Players run the official AU-Avengers release that this
  installer already installs. The bridge is an extra plugin next to it.
* **The bridge is client-only.** It uses no RPCs, so a lobby works with a mix of players with and
  without it. Official BetterCrewLink ignores the bridge, and the app works normally without
  it, so either half can be missing without breaking anything.
* **The bridge is tied to a TOU-Mira version.** It references TOU-Mira's and MiraAPI's
  assemblies by version, so each supported TOU-Mira release gets its own build. A bridge for
  the wrong version can fail to load. That's why the installer picks by TOU-Mira version
  (`toumira_version.txt`).

whg-tou-mira layout (for orientation; you normally don't edit it from here):

| Path | What |
|---|---|
| `TouMiraBclBridge/` | Bridge source (C#) |
| `BetterCrewlink/` | Submodule: the BetterCrewLink-TOU fork |
| `TOU-Mira/` | Submodule pinned to an official TOU-Mira tag. Read-only compile reference |
| `scripts/release-bcl-tou.sh` | Builds and publishes a release (see below) |
| `AGENT.md`, `README.md`, `docs/PROJECT_LOG.md` | Agent rules, human docs, history and current release state |

## The release contract (what this installer depends on)

Everything the installer installs for voice chat comes from GitHub releases on
**`rroig7/BetterCrewLink`**, read from `/releases` (the full list; most releases are
prereleases). Each release carries:

| Asset | Used by |
|---|---|
| `BetterCrewLink-TOU-Setup-<version>.exe` | `bettercrewlink.latest_setup`: the newest non-draft release with a `*setup*.exe`, run with `/S` |
| `BetterCrewLink-TOU-Setup-<version>.exe.blockmap`, `latest.yml` | The app's own auto-updater (electron-updater), not the installer |
| `TouMiraBclBridge-<tou-mira-tag>.dll`, one per supported TOU-Mira release (e.g. `TouMiraBclBridge-1.7.3.dll`, `TouMiraBclBridge-1.7.9-beta1.dll`) | `bridge.find_for`: the newest non-draft release with the asset for the installed TOU-Mira tag. Installed as `TouMiraBclBridge.dll` |

Also part of the contract:

* GitHub's SHA-256 asset `digest` is required for verification. `voice_update` also compares it
  with the installed bridge's hash to decide whether a bridge update is due.
* Versions are semver, `x.y.z-alpha.N` for now. Tags are `v<version>`. Compare with
  `version_utils.semver_gt`, not `version_gt`.
* `<tou-mira-tag>` is the exact AU-Avengers/TOU-Mira tag, without a leading `v`, matching what the
  installer writes to `toumira_version.txt`.
* The release notes start with `Built for TOU-Mira: <tag>, <tag>…`, but the installer doesn't
  read them; it goes by asset names.

**Legacy:** installer 1.3.0 read a single `TouMiraBclBridge.dll` from
`rroig7/whg-tou-mira`'s own releases. Installers from 1.4.0 on don't. Don't reintroduce that
path.

If you change any of these names or rules on either side, change the other side in the same
piece of work. The producer is `scripts/release-bcl-tou.sh`, and its contract is documented in
whg-tou-mira's `README.md` under "Releasing BetterCrewLink-TOU".

## Which side do I change?

| Task | Where |
|---|---|
| New voice rule, BetterCrewLink-TOU UI or bridge behaviour | whg-tou-mira. Then cut a release there. The installer picks it up without changes. |
| Support a new TOU-Mira version | whg-tou-mira: release with the new tag added, e.g. `scripts/release-bcl-tou.sh <next-version> <new-tag> <old-tags>…`. No installer change, unless TOU-Mira's own zip layout changed. |
| How or where the add-on is installed, detected, updated or uninstalled | Here |
| Release asset names, or where releases live | **Both**, together |

A new BetterCrewLink-TOU release normally needs **no installer change or installer release**.
Already-installed players get the app update through the app's own auto-updater, and the bridge
update through this installer's "Voice chat update available" banner. Rebuilt bridges get new
digests even when the code didn't change, so that banner appears after every release.

## Checking a release against the installer

Run this from this repo, using the installer's own selection code against the live releases:

```sh
.venv/Scripts/python - <<'EOF'
from toumira import bettercrewlink as b, bridge
rel = b.fetch_releases(b.TOU)
print("setup:", b.latest_setup(rel, b.TOU))
for v in ("1.7.3", "1.7.9-beta1"):  # the TOU-Mira tags that release supports
    print(v, "->", bridge.find_for(rel, v))
EOF
```

`find_for` returning `None` means players on that TOU-Mira version get no bridge, and the result
message says so.

## Things to keep in mind

* The BetterCrewLink-TOU setup exe and the bridge are **unsigned**. Silent installs from here
  avoid SmartScreen; manual runs trigger it.
* Nobody has tested the add-on in a live game yet. Don't describe in-game behaviour as verified.
* Both repos' agent docs say to ask the user before committing, pushing or running installs.
