# Auto-C

Auto-C listens to your microphone on Windows and holds **C** while you speak in a League of Legends match. League handles the voice call. Auto-C processes microphone frames locally and discards them as it goes.

![Auto-C mini display showing the live microphone level and activation threshold while waiting for a League match](docs/mini-display.jpg)

## Play

1. On Windows 10 or 11, install Python 3 with the Windows Python launcher (`py`) and Tkinter. Download the repository using **Code → Download ZIP**, extract it, and open the folder. Python 3.10 x64 was used for testing.
2. In League, enable **Team Voice** and confirm its push-to-talk binding is **C**. Riot preserves bindings you previously customized. [Patch 26.23 notes](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-23-notes/)
3. Double-click **Auto-C.cmd**. On first launch it installs the dependencies. The always-on-top mini display opens in the upper-right corner of your second monitor, or on the main monitor when only one is connected. Drag its title bar to move it.
4. Speak with the match window focused. The **C** indicator turns green when Auto-C holds the key. It activates after two consecutive 20 ms speech frames and releases after 300 ms of quiet. Switching windows also releases C.
5. Close the mini display to stop listening and release the key.

The key is enabled only in the foreground match executable, so champion select is outside its scope. In-game text chat shares the match window and can receive C if you speak while typing.

## Tune the microphone

Double-click **Test microphone.cmd**. Speak normally, then pause. The purple **MIC** indicator shows when the detector hears speech. The meter shows the microphone level and the gold marker shows the threshold. Test mode sends no keys.

The default threshold is **−45 dBFS**. If your voice is too quiet to trigger, try **−55**. If background conversation triggers the mic, try **−35**. Run either command from PowerShell in the project folder to open the mini display with your chosen threshold.

```powershell
.\Auto-C.cmd --display --dry-run --threshold -55
.\Auto-C.cmd --display --threshold -55
```

Auto-C starts with the Windows default input. To use the microphone selected in League, run `.\Auto-C.cmd --list-devices`, then pass its numeric ID with `--device ID` in either mode. To run a console microphone test, use `.\Auto-C.cmd --dry-run` and press **Ctrl+C** to stop.

## Existing project

Auto-C imports Google's WebRTC voice activity detector through the Windows wheel from **py-webrtcvad-wheels**. Its speech classification and the adjustable volume threshold must both pass. Microphone capture uses **python-sounddevice**. [WebRTC detector wrapper](https://github.com/daanzu/py-webrtcvad-wheels) · [python-sounddevice](https://github.com/spatialaudio/python-sounddevice)
