# Wayland implementation checkpoints

Phase 1 (#91) validated GNOME 50.1 on Ubuntu 26.04 with a single 1920×1080 monitor and portal-mediated input/capture; phase 2 (#92) centralized the desktop boundary.

Phase 3 (#94) implements a private worker-owned Gio portal connection, explicit host registration, cancellable RemoteDesktop/ScreenCast negotiation and logical-coordinate input primitives. It is not connected to playback yet. The caller must supply an application ID matching its installed desktop file and always close the session. No permission persistence or global shortcuts.

The native input calls use the documented XDG Desktop Portal RemoteDesktop interface. This phase does not translate workflow key names, interpolate pointer motion or interpret physical pixel coordinates; those are integration tasks. A single selected monitor at logical origin is required, but this alone does not prove a single-monitor desktop or 1:1 pixel mapping.

Before enabling workflow execution:
- Connect the authorized PipeWire stream to GStreamer and verify fresh frames and logical/pixel mapping. Fail closed for unsupported display layouts or scaling.
- Connect input and capture to worker-owned execution, including pause/stop, drag/hotkey cleanup, cancellation during portal negotiation and revocation while waiting or actively sending input. Check revocation without depending on further input operations. Do not silently skip ambiguous delivery.
- Provide matching desktop-file identity and optional Linux dependencies; test pipx/deb packaging. Validate real GNOME permission dialogs and cleanup.
- Keep window targeting, Wait for Window, global hotkeys and recording deferred on Wayland. Existing legacy paths stay unchanged.

Tests use a fake portal with no native input. They do not establish real compositor behavior. Follow local-testing.md; hosted Actions remain disabled.

Phase 4 (#96) adds the authorized PipeWire FD and GStreamer capture adapter. Use a nested capture context inside the portal session, both on the owning worker. Appsink keeps at most one queued sample. Screenshots require increasing running-time timestamps, no older than 500 ms, and (when the pipeline clock is available at call entry) captured at or after the request. No cached frame is returned; an idle compositor that supplies no fresh frame may time out. Frames must exactly match the portal logical size; conflicting metadata, invalid crop bounds or unexpected frame format abort capture and invalidate the combined session. No multi-monitor or scaled coordinate support is claimed. Verify actual display topology separately before activating playback.

Linux runtime requirements for capture: system Python GI bindings (python3-gi), gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-pipewire and the GStreamer video conversion plugin (gstreamer1.0-plugins-base). Existing Pillow is reused. No new mandatory pip dependencies. The tested PipeWire 1.6.2 plugin duplicates the supplied FD internally (gstpipewirecore.c); the capture adapter owns the original and closes it after pipeline teardown. GStreamer state transitions remain synchronous native calls; verify shutdown on real GNOME, including disconnect and timeout. No capture or input is wired to runtime/UI yet.
