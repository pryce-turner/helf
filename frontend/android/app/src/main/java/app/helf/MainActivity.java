package app.helf;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // In-app plugins register before the bridge starts.
        registerPlugin(HelfNativePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
