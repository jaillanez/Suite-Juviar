package ar.com.juviar.tablet;

import android.os.Bundle;
import android.webkit.WebSettings;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import com.getcapacitor.BridgeActivity;
import java.util.Set;

public class MainActivity extends BridgeActivity {

    /** Las pantallas están pensadas para computadora: en la tablet se muestran un 30 % más chicas. */
    private static final String ESCALA = "0.7";

    private static final String AJUSTAR_PANTALLA =
        "(function () {" +
        "  var contenido = 'width=device-width, initial-scale=" + ESCALA + ", minimum-scale=" + ESCALA + "';" +
        "  function ajustar() {" +
        "    var metas = document.querySelectorAll('meta[name=viewport]');" +
        "    if (!metas.length && document.head) {" +
        "      var m = document.createElement('meta'); m.name = 'viewport'; document.head.appendChild(m); metas = [m];" +
        "    }" +
        "    for (var i = 0; i < metas.length; i++) if (metas[i].content !== contenido) metas[i].content = contenido;" +
        "  }" +
        "  new MutationObserver(ajustar).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['content'] });" +
        "  document.addEventListener('DOMContentLoaded', ajustar);" +
        "})();";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebSettings ajustes = bridge.getWebView().getSettings();
        ajustes.setUseWideViewPort(true);
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(bridge.getWebView(), AJUSTAR_PANTALLA,
                Set.of("https://juviar-gestion.duckdns.org", "https://juviar-bot.duckdns.org"));
        }
    }
}
