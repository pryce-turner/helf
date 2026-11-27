package app.helf;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * What this build of the app can do natively, for the web code to check.
 *
 * The UI is loaded from the server (capacitor.config.ts server.url), so new
 * web code reaches an old APK the moment Helf redeploys. Anything that needs
 * native support the old APK lacks has to ask first. Its mere presence is the
 * first answer: an APK without this plugin predates background sync (plan
 * 0025 phase 3), whose notification icon it does not have, and starting the
 * foreground service there would crash the app.
 */
@CapacitorPlugin(name = "HelfNative")
public class HelfNativePlugin extends Plugin {

    @PluginMethod
    public void features(PluginCall call) {
        JSArray features = new JSArray();
        features.put("background-sync");
        JSObject result = new JSObject();
        result.put("features", features);
        call.resolve(result);
    }
}
