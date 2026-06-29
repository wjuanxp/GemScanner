# Baumer EXG50 — GenICam feature reference

The EXG50 is a **legacy Baumer GigE camera**. Its native SDK is **GAPI / bgapi2**
(what Camera Explorer uses). **neoAPI does not support it** — pointed at the EXG50,
neoAPI loads a stripped GigE-Vision fallback node map (~54 features, `Gain`/auto
inaccessible) and streams a black sensor. GemScanner therefore drives this camera via
**Harvesters + Baumer's `bgapi2_gige.cti` GenTL producer**
(`C:\Program Files\Baumer Camera Explorer\bgapi2_gige.cti`), backend
`gemscanner/camera/gentl_camera.py` (`GenTLCamera`, config key `camera_backend: gentl`).

> **Legacy node names.** This camera predates current SFNC naming. The image/sensor
> controls are `ExposureTimeAbs`, `GainAbs`/`GainRaw`, `TestImageSelector` — **not**
> the modern `ExposureTime`/`Gain`/`TestPattern` neoAPI expected. There is **no**
> `ExposureAuto`/`GainAuto` (exposure & gain are manual only).

Access (Harvesters):
```python
ia = h.create(0)
nm = ia.remote_device.node_map
nm.ExposureTimeAbs.value = 470000      # µs
nm.TestImageSelector.value = "Off"
print(sorted(a for a in dir(nm) if a[:1].isupper()))   # full feature list
```

## Scanner-relevant features (what `GenTLCamera` uses)

| Feature | Meaning / value | GemScanner use |
|---|---|---|
| `ExposureTimeAbs` | exposure in **µs** (float). ~470000 with no dedicated light; drops once the collimated backlight is in. | `set_exposure()` / `exposure_us` |
| `GainAbs` | absolute gain (float). Prefer leaving low for clean silhouettes. | `gain` (optional) |
| `GainRaw` / `GainSelector` / `GainFactor` | raw/selectable gain (set `GainSelector` first if using `GainRaw`). | fallback only |
| `BlackLevelRaw` / `BlackLevelSelector` | black-level offset. | leave default |
| `TestImageSelector` | **set `"Off"`** for the real sensor (other values = synthetic patterns). | forced off in `open()` |
| `PixelFormat` | `Mono8` for the scanner. | set in `open()` |
| `Width` / `Height` | image size (default full: 2464 × 2064). | read |
| `OffsetX` / `OffsetY` | ROI origin. | future ROI |
| `SensorWidth` / `SensorHeight` | sensor size. | info |
| `BinningHorizontal` / `BinningVertical` | pixel binning. | leave 1 |
| `PartialScanEnabled` | partial-scan ROI enable. | leave off |
| `ReadOutTime` | sensor readout time. | timing info |
| `PayloadSize` | bytes per frame. | info |
| `ShutterMode` / `HqMode` | shutter / high-quality mode. | leave default |
| `UserSetSelector` / `UserSetSave` / `UserSetLoad` / `UserSetDefaultSelector` | save/restore config; set a default that boots `TestImage=Off` + good exposure. | persistence |

## Acquisition & trigger
`AcquisitionMode`, `AcquisitionStart`, `AcquisitionStop`, `AcquisitionAbort`,
`AcquisitionPause`, `AcquisitionResume`, `AcquisitionAndTriggerControls` (category),
`TriggerMode`, `TriggerSelector`, `TriggerSource`, `TriggerActivation`,
`TriggerSoftware`, `FrameCounter`.
→ Scanner runs **free-run** (`TriggerMode=Off`), one `grab()` per stop-and-settle step.

## Analog / sensor
`AnalogControls` (category), `ExposureTimeAbs`, `GainAbs`, `GainRaw`, `GainFactor`,
`GainSelector`, `BlackLevelRaw`, `BlackLevelSelector`, `ShutterMode`, `HqMode`.

## Image format / ROI
`ImageFormatControl` (category), `Formats` (category), `PixelFormat`, `Width`,
`Height`, `OffsetX`, `OffsetY`, `SensorWidth`, `SensorHeight`, `BinningHorizontal`,
`BinningVertical`, `PartialScanEnabled`, `PayloadSize`, `ReadOutTime`,
`TestImageSelector`.

## Correction / LUT / chunk / counters
`LUTControls` (category), `DefectPixelCorrection`, `DefectPixelListEntryActive`,
`DefectPixelListEntryPosX`, `DefectPixelListEntryPosY`, `DefectPixelListIndex`,
`DefectPixelListUpdate`, `ChunkDataStreams` (category), `ChunkEnable`,
`ChunkModeActive`, `ChunkSelector`, `CountersAndTimers` (category).

## Digital I/O / flash (strobe)
`DigitalIO` (category), `Flash`, `FlashPolarity`, `LineSelector`, `LineMode`,
`LineSource`, `LineInverter`, `LineStatus`, `LineStatusAll`, `UserOutputSelector`,
`UserOutputValue`, `UserOutputValueAll`.
→ Available if the backlight is later strobed in sync with exposure.

## Device information
`DeviceInformation` (category), `DeviceVendorName` (= "Baumer Optronic"),
`DeviceModelName` (= "EXG50"), `DeviceManufacturerInfo`, `DeviceUserID`, `BoSpec0`.

## GigE transport layer (Gev*)
`GigEVisionTransportLayer` (category), `GevCCP`, `GevCurrentIPAddress`,
`GevCurrentSubnetMask`, `GevCurrentDefaultGateway`, `GevCurrentIPConfiguration`,
`GevCurrentIPConfigurationDHCP/LLA/PersistentIP`, `GevPersistentIPAddress`,
`GevPersistentSubnetMask`, `GevPersistentDefaultGateway`,
`GevSupportedIPConfigurationDHCP/LLA/PersistentIP`, `GevIPConfigurationStatus`,
`GevSCPD`, `GevSCPSPacketSize`, `GevSCPHostPort`, `GevSCPInterfaceIndex`, `GevSCDA`,
`GevSCPSBigEndian`, `GevSCPSDoNotFragment`, `GevSCPSFireTestPacket`,
`GevStreamChannelCount`, `GevStreamChannelSelector`, `GevMessageChannelCount`,
`GevMCDA`, `GevMCPHostPort`, `GevMCRC`, `GevMCTT`, `GevLinkSpeed`, `GevMACAddress`,
`GevHeartbeatTimeout`, `GevTimestampControlLatch`, `GevTimestampControlReset`,
`GevTimestampValue`, `GevTimestampTickFrequency`, `GevVersionMajor`,
`GevVersionMinor`, `GevDeviceModeIsBigEndian`, `GevDeviceModeCharacterSet`,
`GevFirstURL`, `GevSecondURL`, `GevInterfaceSelector`, `GevNumberOfInterfaces`,
`GevSupportedOptionalCommands*`.
→ Network setup: NIC and camera on the **same subnet**; camera on a **Persistent IP**
(`GevPersistentIPAddress` / `…SubnetMask`); jumbo frames via `GevSCPSPacketSize=9000`.

## Notes
- This is the bgapi2/GAPI node map. Names can differ on other Baumer families; the
  modern CX/X series use SFNC names and ARE supported by neoAPI (`camera_backend: baumer`).
- To regenerate this list live: `print(sorted(a for a in dir(nm) if a[:1].isupper()))`.
- To dump current values + access modes (richer reference), iterate the node map and
  read `.value` per node inside try/except.
