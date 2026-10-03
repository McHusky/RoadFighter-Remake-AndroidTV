package io.github.roadfighter.tv;

import android.content.Context;
import android.content.pm.PackageManager;
import android.content.res.AssetManager;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.hardware.input.InputManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Toast;

import org.libsdl.app.SDLActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Thin Android-TV shell around the original Road Fighter SDL2 code.
 *
 * Controller policy for 8BitDo Micro (D mode):
 *  - first controller that presses B -> player 1
 *  - second controller that presses B -> player 2
 *  - D-pad left/right -> steer, up/down -> menu
 *  - B -> accelerate / confirm
 *  - Y -> back / Escape
 *  - Start -> pause (F1)
 *  - Star/Turbo (generic button 14) -> quit app
 *
 * We consume gamepad events here and forward a tiny normalized control set to JNI,
 * so the 2003 game can keep using its original keyboard logic unchanged.
 */
public final class RoadFighterActivity extends SDLActivity implements InputManager.InputDeviceListener {
    private static final String TAG = "RoadFighterTV";
    private static final int CTRL_LEFT = 0;
    private static final int CTRL_RIGHT = 1;
    private static final int CTRL_UP = 2;
    private static final int CTRL_DOWN = 3;
    private static final int CTRL_GAS = 4;
    private static final int CTRL_BACK = 5;
    private static final int CTRL_START = 6;

    private static final String ASSET_ROOT = "roadfighter";
    private static final String ASSET_MARKER = ".roadfighter-assets-v5";

    private final Map<Integer, Integer> playerForDevice = new HashMap<>();
    private final Map<Integer, AxisState> axesForDevice = new HashMap<>();
    private InputManager inputManager;

    private static native void nativeControl(int playerIndex, int control, boolean down);
    private static native void nativeResetPlayer(int playerIndex);
    private static native void nativeResetAll();
    private static native void nativeRequestQuit();
    private static native void nativeConfigureAudio(
            int sampleRate, int framesPerBuffer, boolean lowLatencyFeature);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // The original game uses normal relative file IO. Materialize packaged APK assets
        // into app-private storage before SDL starts the native main function.
        try {
            installGameAssetsIfNeeded();
        } catch (IOException e) {
            throw new RuntimeException("Road Fighter assets could not be installed", e);
        }

        super.onCreate(savedInstanceState);

        // SDL's shared libraries are loaded by SDLActivity.onCreate(), while SDL_main
        // does not start until the later resume/surface-ready transition. Query the
        // device-native Android output configuration in this window and hand it to
        // the native mixer bridge before Road Fighter initializes SDL_mixer.
        configureAndroidAudio();

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        inputManager = (InputManager) getSystemService(Context.INPUT_SERVICE);
        if (inputManager != null) inputManager.registerInputDeviceListener(this, null);
        hideSystemUi();
    }

    private void configureAndroidAudio() {
        int sampleRate = 0;
        int framesPerBuffer = 0;
        boolean lowLatencyFeature = false;

        final AudioManager audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        if (audioManager != null) {
            sampleRate = parsePositiveAudioProperty(
                    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE));
            framesPerBuffer = parsePositiveAudioProperty(
                    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER));

            final StringBuilder outputs = new StringBuilder();
            for (AudioDeviceInfo device : audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
                if (!device.isSink()) continue;
                if (outputs.length() > 0) outputs.append(", ");
                outputs.append("type=").append(device.getType())
                        .append(" product=").append(device.getProductName());
            }
            Log.i(TAG, "audio outputs=[" + outputs + "]");
        }

        final PackageManager packageManager = getPackageManager();
        if (packageManager != null) {
            lowLatencyFeature = packageManager.hasSystemFeature(
                    PackageManager.FEATURE_AUDIO_LOW_LATENCY);
        }

        Log.i(TAG, "Android audio nativeSampleRate=" + sampleRate
                + " framesPerBuffer=" + framesPerBuffer
                + " lowLatencyFeature=" + lowLatencyFeature);
        nativeConfigureAudio(sampleRate, framesPerBuffer, lowLatencyFeature);
    }

    private static int parsePositiveAudioProperty(String value) {
        if (value == null) return 0;
        try {
            final int parsed = Integer.parseInt(value);
            return parsed > 0 ? parsed : 0;
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    @Override
    public void finish() {
        // SDL 2.32.x calls Activity.finish() after SDL_main() returns. Remove the task
        // as part of that normal finish so Google TV does not retain a stale app task.
        finishAndRemoveTask();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideSystemUi();
    }

    @Override
    protected void onPause() {
        nativeResetAll();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        final boolean finishing = isFinishing();

        if (inputManager != null) inputManager.unregisterInputDeviceListener(this);
        nativeResetAll();

        // SDL 2.32.x finishes the Activity after SDL_main() returns, but Android may keep
        // the Linux process alive. Road Fighter's 2003-era global/native state is not
        // safe to re-enter in that cached process, which is what caused a black screen
        // on the next launcher start. Let SDL complete its native shutdown first, then
        // terminate the already-cleaned process so the next launch starts completely fresh.
        super.onDestroy();

        if (finishing) {
            Log.i(TAG, "activity finished; terminating process for a fresh next launch");
            System.exit(0);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemUi();
        else nativeResetAll();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        final InputDevice device = event.getDevice();
        if (device == null || !isGameController(device)) {
            return super.dispatchKeyEvent(event);
        }

        final int keyCode = event.getKeyCode();
        final boolean down = event.getAction() == KeyEvent.ACTION_DOWN;
        if (down && event.getRepeatCount() == 0) {
            // Log every controller key, including unknown ones. This makes it easy to
            // identify firmware-specific 8BitDo mappings from adb/logcat.
            Log.i(TAG, "key device=" + device.getName()
                    + " code=" + keyCode
                    + " name=" + KeyEvent.keyCodeToString(keyCode)
                    + " scan=" + event.getScanCode());
        }

        // Try the Android generic gamepad representation first. Different Android/8BitDo
        // firmware combinations can expose the physical Star/Turbo key differently, so
        // keep a few device-specific fallbacks and log every button-down event above.
        // Quit is handled before player assignment so Star can close the app even from
        // the title/menu screens.
        if (isStarQuitButton(device, event)) {
            if (down && event.getRepeatCount() == 0) {
                Log.i(TAG, "controller Star requested graceful quit");
                nativeResetAll();
                nativeRequestQuit();
            }
            return true;
        }

        if (!isHandledControllerKey(keyCode)) {
            // Consume other controller buttons too; the original SDL controller layer
            // should not see a second, duplicate interpretation of the same device.
            return true;
        }

        Integer player = playerForDevice.get(device.getId());

        // B is deliberately both JOIN and GAS. A newly joined controller therefore
        // starts accelerating immediately, which matches the simple console UX.
        if (player == null && down && keyCode == KeyEvent.KEYCODE_BUTTON_B && event.getRepeatCount() == 0) {
            player = assignPlayer(device.getId());
        }

        if (player == null || player < 0) return true;

        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_LEFT:
                nativeControl(player, CTRL_LEFT, down);
                break;
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                nativeControl(player, CTRL_RIGHT, down);
                break;
            case KeyEvent.KEYCODE_DPAD_UP:
                nativeControl(player, CTRL_UP, down);
                break;
            case KeyEvent.KEYCODE_DPAD_DOWN:
                nativeControl(player, CTRL_DOWN, down);
                break;
            case KeyEvent.KEYCODE_BUTTON_B:
                nativeControl(player, CTRL_GAS, down);
                break;
            case KeyEvent.KEYCODE_BUTTON_Y:
                nativeControl(player, CTRL_BACK, down);
                break;
            case KeyEvent.KEYCODE_BUTTON_START:
                nativeControl(player, CTRL_START, down);
                break;
            case KeyEvent.KEYCODE_BUTTON_SELECT:
            case KeyEvent.KEYCODE_BUTTON_MODE:
            default:
                break;
        }
        return true;
    }

    @Override
    public boolean dispatchGenericMotionEvent(MotionEvent event) {
        final InputDevice device = event.getDevice();
        if (device == null || !isGameController(device)) {
            return super.dispatchGenericMotionEvent(event);
        }

        Integer player = playerForDevice.get(device.getId());
        if (player == null) return true;

        // 8BitDo Micro can expose the physical D-pad either as HAT axes or as
        // the left stick (the mode is switchable on the controller). Do not let
        // a present-but-neutral HAT range mask an active stick value.
        final float hatX = centeredAxis(event, device, MotionEvent.AXIS_HAT_X, 0f);
        final float hatY = centeredAxis(event, device, MotionEvent.AXIS_HAT_Y, 0f);
        final float stickX = centeredAxis(event, device, MotionEvent.AXIS_X, 0f);
        final float stickY = centeredAxis(event, device, MotionEvent.AXIS_Y, 0f);
        final float x = Math.abs(hatX) > 0.5f ? hatX : stickX;
        final float y = Math.abs(hatY) > 0.5f ? hatY : stickY;

        final AxisState old = axesForDevice.computeIfAbsent(device.getId(), ignored -> new AxisState());
        final boolean left = x < -0.5f;
        final boolean right = x > 0.5f;
        final boolean up = y < -0.5f;
        final boolean down = y > 0.5f;

        if (old.left != left || old.right != right || old.up != up || old.down != down) {
            Log.i(TAG, "axis device=" + device.getName()
                    + " hat=(" + hatX + "," + hatY + ")"
                    + " stick=(" + stickX + "," + stickY + ")"
                    + " resolved=(" + x + "," + y + ")");
        }

        if (old.left != left) nativeControl(player, CTRL_LEFT, left);
        if (old.right != right) nativeControl(player, CTRL_RIGHT, right);
        if (old.up != up) nativeControl(player, CTRL_UP, up);
        if (old.down != down) nativeControl(player, CTRL_DOWN, down);

        old.left = left;
        old.right = right;
        old.up = up;
        old.down = down;
        return true;
    }

    private int assignPlayer(int deviceId) {
        if (!playerForDevice.containsValue(0)) {
            playerForDevice.put(deviceId, 0);
            Toast.makeText(this, "Spieler 1 verbunden", Toast.LENGTH_SHORT).show();
            return 0;
        }
        if (!playerForDevice.containsValue(1)) {
            playerForDevice.put(deviceId, 1);
            Toast.makeText(this, "Spieler 2 verbunden", Toast.LENGTH_SHORT).show();
            return 1;
        }
        // Both slots are already occupied. Ignore additional gamepads.
        return -1;
    }

    private boolean isStarQuitButton(InputDevice device, KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BUTTON_14) return true;

        final String name = device.getName() == null ? "" : device.getName().toLowerCase();
        if (!name.contains("8bitdo")) return false;

        // Generic.kl maps Linux scan codes 269 and 301 to BUTTON_14. Some vendor
        // layouts may instead surface an actual STAR key (keycode/scan 522).
        if (event.getKeyCode() == KeyEvent.KEYCODE_STAR) return true;
        final int scanCode = event.getScanCode();
        return scanCode == 269 || scanCode == 301 || scanCode == 522;
    }

    private boolean isHandledControllerKey(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_LEFT:
            case KeyEvent.KEYCODE_DPAD_RIGHT:
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_BUTTON_B:
            case KeyEvent.KEYCODE_BUTTON_Y:
            case KeyEvent.KEYCODE_BUTTON_START:
            case KeyEvent.KEYCODE_BUTTON_SELECT:
            case KeyEvent.KEYCODE_BUTTON_MODE:
                return true;
            default:
                return false;
        }
    }

    private boolean isGameController(InputDevice device) {
        final int sources = device.getSources();
        if ((sources & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (sources & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK) {
            return true;
        }

        // Some 8BitDo firmware modes expose the D-pad as SOURCE_DPAD rather
        // than SOURCE_GAMEPAD. Accept that device specifically, but do not
        // classify the normal Google TV remote as a player controller.
        final String name = device.getName() == null ? "" : device.getName().toLowerCase();
        return name.contains("8bitdo")
                && (sources & InputDevice.SOURCE_DPAD) == InputDevice.SOURCE_DPAD;
    }

    private float centeredAxis(MotionEvent event, InputDevice device, int axis, float fallback) {
        // getMotionRange(axis, eventSource) can miss HAT ranges on controllers
        // that report a combined source mask. The axis-only lookup is more
        // reliable on Android TV / 8BitDo devices.
        final InputDevice.MotionRange range = device.getMotionRange(axis);
        if (range == null) return fallback;
        final float value = event.getAxisValue(axis);
        return Math.abs(value) > Math.max(0.15f, range.getFlat()) ? value : 0f;
    }

    private void hideSystemUi() {
        if (Build.VERSION.SDK_INT >= 30) {
            final WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    private void installGameAssetsIfNeeded() throws IOException {
        final File marker = new File(getFilesDir(), ASSET_MARKER);
        if (marker.isFile()) return;
        copyAssetTree(getAssets(), ASSET_ROOT, getFilesDir());
        if (!marker.createNewFile() && !marker.isFile()) {
            throw new IOException("Could not create asset installation marker");
        }
    }

    private void copyAssetTree(AssetManager assets, String assetPath, File destinationRoot) throws IOException {
        final String[] children = assets.list(assetPath);
        if (children == null) throw new IOException("Cannot list asset path: " + assetPath);

        if (children.length == 0) {
            final String relative = assetPath.substring(ASSET_ROOT.length());
            final File out = new File(destinationRoot, relative.startsWith("/") ? relative.substring(1) : relative);
            final File parent = out.getParentFile();
            if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
                throw new IOException("Cannot create directory: " + parent);
            }
            try (InputStream in = assets.open(assetPath); FileOutputStream fos = new FileOutputStream(out)) {
                final byte[] buffer = new byte[64 * 1024];
                int n;
                while ((n = in.read(buffer)) >= 0) fos.write(buffer, 0, n);
            }
            return;
        }

        for (String child : children) {
            copyAssetTree(assets, assetPath + "/" + child, destinationRoot);
        }
    }

    @Override
    public void onInputDeviceAdded(int deviceId) {
        // Assignment intentionally waits for B so Android enumeration order is irrelevant.
    }

    @Override
    public void onInputDeviceChanged(int deviceId) {
        // Nothing to do. Mapping is based on the Android device id for this session.
    }

    @Override
    public void onInputDeviceRemoved(int deviceId) {
        final Integer player = playerForDevice.remove(deviceId);
        axesForDevice.remove(deviceId);
        if (player != null) {
            nativeResetPlayer(player);
            Toast.makeText(this, "Spieler " + (player + 1) + " getrennt", Toast.LENGTH_SHORT).show();
        }
    }

    private static final class AxisState {
        boolean left;
        boolean right;
        boolean up;
        boolean down;
    }
}
