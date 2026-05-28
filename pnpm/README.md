# pnpm supply-chain security

Hardening for pnpm against compromised npm packages. Covers two layers:

1. **Global config** on this Mac (applies to every project automatically).
2. **Per-project template** committed to each repo (applies for teammates and CI).

Both layers are needed. Global is a personal safety net; per-project is the
team-wide guarantee.

## Why

npm packages get compromised regularly. The pattern is consistent: an
attacker publishes a malicious version, security scanners detect it within
hours, npm pulls the version. The risk window is the gap between publish
and takedown.

Three settings cut most of that risk:

| Setting | What it does | Why it matters |
|---|---|---|
| `minimumReleaseAge` | Refuses to install package versions newer than N minutes | Closes the publish-to-takedown window. 10080 = 7 days. |
| `dangerouslyAllowAllBuilds` | When `false`, blocks postinstall / install / prepare scripts unless explicitly approved | Most malware ships in postinstall scripts. Default in pnpm v10+, restated here so it can't drift. |
| `blockExoticSubdeps` | Rejects transitive dependencies from git URLs, tarballs, or other non-registry sources | Forces every sub-dep through the registry where signatures, provenance, and takedowns apply. |

## Global setup (this Mac)

Already applied. To reapply on a fresh machine:

```sh
pnpm config set minimumReleaseAge 10080 --global
pnpm config set dangerouslyAllowAllBuilds false --global
pnpm config set blockExoticSubdeps true --global
```

The settings land in `~/Library/Preferences/pnpm/rc`. A non-secret snapshot
is checked in as [`global-rc.example`](./global-rc.example) for reference.
The real rc file is not stowed because it also contains the npm auth token.

Verify:

```sh
pnpm config get minimumReleaseAge
pnpm config get dangerouslyAllowAllBuilds
pnpm config get blockExoticSubdeps
```

## Per-project setup

Copy the relevant keys from [`pnpm-workspace.yaml.template`](./pnpm-workspace.yaml.template)
into the project's `pnpm-workspace.yaml`. Commit it. This makes the same
protections apply for every contributor and in CI, not just on this Mac.

The template also includes two allowlist keys:

- `minimumReleaseAgeExclude`: packages exempted from the release-age delay.
- `onlyBuiltDependencies`: packages whose build scripts may run.

Keep both lists short, scoped per project, and reviewed in PRs.

## Day-to-day friction and how to handle it

**"Couldn't find package X in version Y"** on a fresh `pnpm install` for a
version published less than 7 days ago.

- One-off: `pnpm add <pkg> --allow-non-published-version`
- Recurring (package you trust): add it to `minimumReleaseAgeExclude` in
  the project's `pnpm-workspace.yaml`.

**"Ignored build scripts: X, Y, Z"** warning during install.

- Run `pnpm approve-builds` inside the project. It lists the dependencies
  asking to build and writes approved ones to `onlyBuiltDependencies`.
- Only approve packages that legitimately need a native build (e.g.
  `esbuild`, `sharp`, `better-sqlite3`, `node-gyp` consumers).

**"Cannot install dependency from non-registry source"** when adding a dep.

- A transitive dependency points at a git or tarball URL. Either find a
  registry-published alternative, or vendor it deliberately. Don't relax
  `blockExoticSubdeps` to work around a single package.

## References

- [pnpm supply-chain security guide](https://pnpm.io/supply-chain-security)
- [pnpm settings reference](https://pnpm.io/settings)
