# TikTok Publisher Phase E

## Scope

The publisher uses state-driven UI automation on TikTok package:

```text
com.zhiliaoapp.musically
```

It does not assume a fixed screen sequence.

## Verified state machine

```text
HOME
  ↓ create
CREATE
  ↓ upload
GALLERY
  ↓ select isolated media
EDIT
  ↓ next
POST_CONFIG
  ↓ explicit commit only
PUBLISH
```

Verified 2026-10-02 on Lenovo TB323FU / Android 16.

## State evidence

- HOME: bottom navigation contains create button `o70`
- CREATE: `upload_hot_area`
- GALLERY: `viewpager_choose_media`
- EDIT: next button `pjg`
- POST_CONFIG: final publish button `st6`

Foreground overlays may coexist with background nodes in uiautomator XML.
Detection therefore prioritizes later workflow states over CREATE/HOME.

## Media permissions

Required for the current TikTok gallery flow:

```text
android.permission.READ_MEDIA_VIDEO
android.permission.READ_MEDIA_IMAGES
```

No additional camera or microphone permission was added for upload.

## Isolated media album

Automation-owned test/publish media is staged under:

```text
/sdcard/Movies/Y700Agent/
```

MediaStore must be refreshed after placing a file there.

The TikTok gallery exposes this directory as album:

```text
Y700Agent
```

This avoids selecting unrelated user media from Recent Projects.

## Commit boundary

`POST_CONFIG` is a hard workflow boundary.

Normal probe, recovery, state-detection and smoke-test flows MUST NOT activate:

```text
com.zhiliaoapp.musically:id/st6
```

which is the final Publish button.

A real publish operation must be a distinct explicit action in the publish job flow.

## Verified path

A 2-second local test video was created with Android `screenrecord`, scanned into MediaStore, selected from the isolated `Y700Agent` album, and advanced successfully to POST_CONFIG.

No real TikTok post was published during this validation.
