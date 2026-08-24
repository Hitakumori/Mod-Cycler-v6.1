# Mod Cycler

If you want to support me: [🎮 Patreon](https://www.patreon.com/cw/Hitakumori)

## How to Use

**Download:** Place `Mod_Cycler_v6.6.exe` anywhere you want. The app is portable; settings are stored in `%APPDATA%\NRMM_Mod_Cycler`.

**Launch:** Open `Mod_Cycler_v6.6.exe`.

**Browse:** Select your game's `Mods` folder. Examples: `GIMI\Mods`, `SRMI\Mods`, `WWMI\Mods`, or `ZZMI\Mods`.

**Select:** Check the mod groups you want to cycle.

**Generate:** Click **GENERATE .INI** to create `Mod Cycler\mod_cycler.ini` in the selected `Mods` folder.

**Reload:** Press F10 in-game to reload XXMI/GIMI and apply the new ini.

> 💡 After `mod_cycler.ini` is generated and reloaded in-game, Mod Cycler does not need to stay open. The generated ini handles cycling inside XXMI/GIMI.

## Favorites Only

Enable **Favorites only** below the interval control before generating to cycle only mods marked as favorites in NRMM. Mod Cycler detects NRMM's empty `fav` marker file in each managed mod folder.

Groups with no favorited mods are skipped. A group with one favorite stays on that mod while the other selected groups continue cycling.

## Generated INI Controls

All generated ini controls are rebindable in the app before pressing **GENERATE .INI**.

- **PGUP / PGDN:** Cycle forward and backward through the selected groups.
- **INSERT:** Randomize all selected groups.
- **CAPSLOCK:** Toggle Auto-Cycle.
- **END:** Toggle Auto-Shuffle.

## App Hotkey

**Alt + S:** Show or hide the Mod Cycler window while the app is running.

This hotkey is for the app UI only. It is not written into `mod_cycler.ini` and is not needed after you close Mod Cycler.

## UI & Customization

- **Theme:** Change the UI color and transparency from the app.
- **Profiles:** Save and load selected groups, keybinds, interval, and Favorites only mode.
- **Group Names:** Right-click any detected group to rename it.
- **Reset Group Name:** Rename a group to a blank value to remove the custom name and return to automatic name detection.

## Group Detection Notes

Mod Cycler reads groups from the selected `Mods` folder's `_MANAGED_` directory.

- If multiple detected folders use the same group number, Mod Cycler skips the duplicates because the generated ini can only target one mod-manager group per ID.
- Custom group names are saved per selected `Mods` folder, so labels from GIMI, SRMI, WWMI, and ZZMI do not overwrite each other.
- If `_MANAGED_` changes after generating, Mod Cycler warns when the active cycler is out of date.

## Updates

Use **CHECK UPDATES** to check GitHub releases/tags for [Hitakumori/Mod-Cycler](https://github.com/Hitakumori/Mod-Cycler).

If the latest release includes a Windows `.exe` asset, Mod Cycler can download it, close, replace itself, and restart. If no `.exe` asset is available, it opens the GitHub page instead.
