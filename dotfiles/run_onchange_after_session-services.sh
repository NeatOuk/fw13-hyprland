#!/bin/sh
# User services tied to the graphical session (no user systemd, e.g. CI containers: skip).
#  - fw-crash-watch: crash/failed-service notifications (Diagnose with Jarvis)
#  - mako: notifications; its own unit follows graphical-session.target under uwsm (not started from Hyprland)
#  - fw-theme-session: GTK theme/colour scheme set at Hyprland login, handed back at logout (fw13.theme)
#  - fw-autobrightness: ambient-light brightness (Hyprland only, off until Settings → Display turns it on)
#  - fw-battery-warn: low-battery notifications at 20/10/5 % (Hyprland only; levels in Settings → Power)
#  - fw-bt-agent: Bluetooth pairing prompts (confirm code, PIN; Hyprland only; replaces blueman-applet)
#  - fw-syncthing: Syncthing requests (new device, shared folder) as notifications (Hyprland + Syncthing only)
#  - fw-usb: USB drive notice (mount, Open in Thunar, Eject; Hyprland only)
#  - fw-timezone: automatic time zone from GeoClue (Hyprland only, off until Settings → System turns it on)
#  - fw-health.timer: health report 15 min after login, then daily (fw-health --timer; notifies in Hyprland only)
#  - fw-updates.timer: dnf update check 20 min after login, then daily (fw-updates --check; Update now = snapshot first)
#  - fw-nightlight.timer: night light schedule every 5 min (python3 -m fw13.nightlight tick; off unless Settings → Display sets one)
systemctl --user show-environment >/dev/null 2>&1 || exit 0
systemctl --user daemon-reload
systemctl --user enable fw-crash-watch.service mako.service fw-theme-session.service fw-autobrightness.service \
  fw-battery-warn.service fw-usb.service fw-timezone.service fw-bt-agent.service fw-syncthing.service
systemctl --user enable --now fw-health.timer fw-updates.timer fw-nightlight.timer
# Syncthing (packages/30-apps.txt; not when the user removed it): its own user unit from the Fedora package
command -v syncthing >/dev/null && systemctl --user enable --now syncthing.service 2>/dev/null || true
systemctl --user reset-failed mako.service 2>/dev/null || true
systemctl --user restart fw-crash-watch.service 2>/dev/null || true
systemctl --user restart fw-battery-warn.service 2>/dev/null || true
systemctl --user restart fw-usb.service 2>/dev/null || true
systemctl --user restart fw-bt-agent.service 2>/dev/null || true
systemctl --user restart fw-syncthing.service 2>/dev/null || true
systemctl --user restart fw-timezone.service 2>/dev/null || true
