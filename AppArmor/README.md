# AppArmor profile for pyJoules containers

This directory contains a custom [AppArmor profile](https://docs.docker.com/engine/security/apparmor/) and a helper script to let a
Docker container read Intel RAPL power data from the host **without** running
the container with `--privileged`.

## Why we need this

- `pyJoules` reads energy counters from the Linux powercap/rapl sysfs tree:
  - `/sys/devices/virtual/powercap/...`
  - `/sys/class/powercap/...` (symlinks into the above)

- Docker's *default* AppArmor profile (`docker-default`) deliberately **denies**
  reads to `/sys/devices/virtual/powercap/**` to keep containers from poking at
  power/thermal info on the host.

- Even if you bind-mount those paths into the container, the default profile
  prevents the container from seeing them.

- On top of that, Docker also [**masks** some system paths inside the container](https://docs.docker.com/reference/cli/docker/container/run/?utm_source=chatgpt.com#security-opt).
  To make our bind mount actually show up, we also tell Docker:

  ```yaml
  security_opt:
    - systempaths=unconfined
  ```

So we need **two** things:

1. a custom AppArmor profile that is the same as `docker-default` but allows
   read-only access to the powercap paths, and
2. unmasking Docker's system paths for that specific container.

## What this repo provides

* `docker-pyjoules`
  Our custom profile. It is intentionally small and close to `docker-default`. As specified in the [AppArmor docs](https://docs.docker.com/engine/security/apparmor/), The `docker-default` profile is generated from the following [template](https://github.com/moby/profiles/blob/main/apparmor/template.go).
  The only meaningful change is:

  ```text
  # docker-default had something like:
  # deny /sys/devices/virtual/powercap/** rwklx,

  # we remove that and allow read-only:
  /sys/devices/virtual/powercap/** r,
  /sys/class/powercap/** r,
  ```

  Everything else (deny mount, deny writing to most of `/sys`, protect `/proc`,
  etc.) stays the same. This keeps the security posture very close to what
  Docker ships by default.

* `setup_docker-pyjoules.sh`
  A small script that:

  1. copies the profile into `/etc/apparmor.d/containers/`,
  2. loads it with `apparmor_parser`,
  3. checks via `aa-status` that the profile is now active.

  It must be run with `sudo`.

## How to install

From the root of the project:

```bash
cd apparmor
sudo ./setup_docker-pyjoules.sh
```

You should see `docker-pyjoules` listed if you run:

```bash
sudo aa-status | grep docker-pyjoules
```

## How to use in docker-compose

In your `docker-compose.yml` add to the **pyJoules** client container:

```yaml
  pyjoules-metrics-client-remote-write:
    # ...
    volumes:
      - /sys/class/powercap:/sys/class/powercap:ro
      - /sys/devices/virtual/powercap:/sys/devices/virtual/powercap:ro
    security_opt:
      - apparmor=docker-pyjoules
      - systempaths=unconfined
```

### Why `systempaths=unconfined`?

Docker masks some system directories (including parts of `/sys`) *before*
AppArmor even gets a chance to decide. In our case, that meant the container
saw an empty `/sys/devices/virtual/powercap` even though we bind-mounted it.

`systempaths=unconfined` tells Docker: "for this container, don't do that
extra masking — I know what I'm doing". Since we still have AppArmor in place,
and since we only added read-only access to exactly the paths pyJoules needs,
this change is narrow and controlled.

### Security rationale

* We did **not** run the container `--privileged`.
* We did **not** broadly grant write access to `/sys`.
* We did **not** disable AppArmor.
* We **only** allowed read access to:

  * `/sys/devices/virtual/powercap/**`
  * `/sys/class/powercap/**`
* Everything else still follows Docker’s default container profile.

This is a minimal change necessary to let a monitoring container read RAPL
counters from the host.

## Troubleshooting

* If the container still sees an empty directory, check what profile it runs:

  ```bash
  docker exec -it <container> cat /proc/1/attr/current
  ```

  You should see `docker-pyjoules (enforce)`.

* If the profile doesn’t show in `aa-status`, re-run the setup script or run:

  ```bash
  sudo apparmor_parser -r -W /etc/apparmor.d/containers/docker-pyjoules
  ```

* If the bind mount isn’t actually there, inspect the container:

  ```bash
  docker inspect <container> --format '{{json .Mounts}}'
  ```

  Make sure `/sys/devices/virtual/powercap` is listed.
