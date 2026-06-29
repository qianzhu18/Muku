package me.qianzhu.mukuapk;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public final class MainActivity extends Activity {
    private static final String PREFS_NAME = "muku_remote";
    private static final String KEY_BASE_URL = "base_url";
    private static final String KEY_WEB_TOKEN = "web_token";
    private static final String KEY_AUTO_SUBMIT = "auto_submit_share";

    private SharedPreferences preferences;
    private WebView webView;
    private View errorPanel;
    private TextView statusText;
    private TextView errorTitleText;
    private TextView errorBodyText;
    private TextView errorAddressText;
    private ProgressBar progressBar;
    private Button backButton;
    private Button reloadButton;

    private String pendingSharedText;
    private boolean mainFrameLoadFailed;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        preferences = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        webView = findViewById(R.id.webview);
        errorPanel = findViewById(R.id.error_panel);
        statusText = findViewById(R.id.status_text);
        errorTitleText = findViewById(R.id.error_title_text);
        errorBodyText = findViewById(R.id.error_body_text);
        errorAddressText = findViewById(R.id.error_address_text);
        progressBar = findViewById(R.id.progress_bar);
        backButton = findViewById(R.id.back_button);
        reloadButton = findViewById(R.id.reload_button);
        Button configButton = findViewById(R.id.config_button);
        Button errorRetryButton = findViewById(R.id.error_retry_button);
        Button errorConfigButton = findViewById(R.id.error_config_button);

        backButton.setOnClickListener((view) -> {
            if (webView.canGoBack()) {
                webView.goBack();
            }
            updateNavigationButtons();
        });
        reloadButton.setOnClickListener((view) -> reloadCurrentPage());
        configButton.setOnClickListener((view) -> showConfigDialog(false));
        errorRetryButton.setOnClickListener((view) -> loadConfiguredPage(pendingSharedText, true));
        errorConfigButton.setOnClickListener((view) -> showConfigDialog(false));

        configureWebView();

        pendingSharedText = extractSharedText(getIntent());
        if (TextUtils.isEmpty(getConfiguredBaseUrl())) {
            showConfigDialog(true);
        } else {
            loadConfiguredPage(pendingSharedText, true);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);

        String sharedText = extractSharedText(intent);
        if (!TextUtils.isEmpty(sharedText)) {
            pendingSharedText = sharedText;
            loadConfiguredPage(pendingSharedText, true);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
            updateNavigationButtons();
            return;
        }
        super.onBackPressed();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " MukuRemote/0.1");

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                mainFrameLoadFailed = false;
                progressBar.setVisibility(View.VISIBLE);
                hideErrorPanel();
                updateNavigationButtons();
                statusText.setText(R.string.status_loading);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
                updateNavigationButtons();
                if (mainFrameLoadFailed) {
                    return;
                }
                pendingSharedText = null;
                statusText.setText(getString(R.string.status_connected, summarizeBaseUrl()));
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request != null ? request.getUrl() : null;
                if (target == null) {
                    return false;
                }
                String scheme = target.getScheme();
                if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, target));
                } catch (ActivityNotFoundException ignored) {
                    Toast.makeText(MainActivity.this, R.string.no_handler, Toast.LENGTH_SHORT).show();
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    showLoadError(error != null ? error.getDescription() : null);
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request != null && request.isForMainFrame() && response != null) {
                    showLoadError("HTTP " + response.getStatusCode());
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                if (handler != null) {
                    handler.cancel();
                }
                showLoadError(getString(R.string.error_ssl));
            }
        });
    }

    private void reloadCurrentPage() {
        if (!mainFrameLoadFailed && !TextUtils.isEmpty(webView.getUrl())) {
            webView.reload();
            return;
        }
        loadConfiguredPage(pendingSharedText, true);
    }

    private void loadConfiguredPage(String shareText, boolean forceLoad) {
        String baseUrl = getConfiguredBaseUrl();
        if (TextUtils.isEmpty(baseUrl)) {
            showConfigDialog(true);
            return;
        }

        String token = getConfiguredWebToken();
        boolean autoSubmit = preferences.getBoolean(KEY_AUTO_SUBMIT, true);
        String launchShareText = !TextUtils.isEmpty(shareText) ? shareText : pendingSharedText;
        String launchUrl = buildLaunchUrl(baseUrl, token, launchShareText, autoSubmit);

        if (!TextUtils.isEmpty(launchShareText)) {
            pendingSharedText = launchShareText;
            statusText.setText(R.string.status_loading_share);
        } else {
            statusText.setText(R.string.status_loading);
        }

        mainFrameLoadFailed = false;
        hideErrorPanel();
        if (!forceLoad && TextUtils.equals(launchUrl, webView.getUrl())) {
            webView.reload();
            return;
        }
        webView.loadUrl(launchUrl);
    }

    private void showConfigDialog(boolean required) {
        View dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_server_config, null, false);
        EditText baseUrlInput = dialogView.findViewById(R.id.base_url_input);
        EditText tokenInput = dialogView.findViewById(R.id.web_token_input);
        CheckBox autoSubmitCheckbox = dialogView.findViewById(R.id.auto_submit_checkbox);

        baseUrlInput.setText(getConfiguredBaseUrl());
        tokenInput.setText(getConfiguredWebToken());
        autoSubmitCheckbox.setChecked(preferences.getBoolean(KEY_AUTO_SUBMIT, true));

        AlertDialog.Builder builder = new AlertDialog.Builder(this)
            .setTitle(required ? R.string.dialog_title_required : R.string.dialog_title)
            .setView(dialogView)
            .setCancelable(!required)
            .setPositiveButton(R.string.save, null);

        if (required) {
            builder.setNegativeButton(R.string.exit_app, (dialog, which) -> finish());
        } else {
            builder.setNegativeButton(android.R.string.cancel, null);
        }

        AlertDialog dialog = builder.create();
        dialog.setOnShowListener((ignored) -> {
            Button saveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
            saveButton.setOnClickListener((view) -> {
                String normalizedBaseUrl = normalizedBaseUrl(baseUrlInput.getText().toString());
                if (TextUtils.isEmpty(normalizedBaseUrl)) {
                    baseUrlInput.setError(getString(R.string.base_url_required));
                    return;
                }

                preferences.edit()
                    .putString(KEY_BASE_URL, normalizedBaseUrl)
                    .putString(KEY_WEB_TOKEN, tokenInput.getText().toString().trim())
                    .putBoolean(KEY_AUTO_SUBMIT, autoSubmitCheckbox.isChecked())
                    .apply();

                dialog.dismiss();
                loadConfiguredPage(pendingSharedText, true);
            });
        });
        dialog.show();
    }

    private void updateNavigationButtons() {
        backButton.setEnabled(!mainFrameLoadFailed && webView.canGoBack());
        reloadButton.setEnabled(true);
    }

    private void showLoadError(CharSequence detail) {
        mainFrameLoadFailed = true;
        progressBar.setVisibility(View.GONE);
        updateNavigationButtons();

        String detailText = detail != null ? detail.toString().trim() : "";
        if (detailText.isEmpty()) {
            detailText = getString(R.string.error_unknown);
        }

        statusText.setText(getString(R.string.status_error, detailText));
        errorTitleText.setText(R.string.error_title);

        StringBuilder body = new StringBuilder();
        body.append(getString(R.string.error_body));
        body.append("\n\n");
        body.append(getConnectionHint());
        if (!TextUtils.isEmpty(pendingSharedText)) {
            body.append("\n\n");
            body.append(getString(R.string.error_pending_share));
        }
        body.append("\n\n");
        body.append(getString(R.string.error_detail, detailText));
        errorBodyText.setText(body.toString());
        errorAddressText.setText(getString(R.string.error_current_url, getConfiguredBaseUrl()));
        showErrorPanel();
    }

    private String getConnectionHint() {
        Uri uri = Uri.parse(getConfiguredBaseUrl());
        String host = uri.getHost();
        if (TextUtils.isEmpty(host)) {
            return getString(R.string.error_hint_generic);
        }
        if (host.endsWith(".ts.net") || host.startsWith("100.")) {
            return getString(R.string.error_hint_tailscale);
        }
        return getString(R.string.error_hint_generic);
    }

    private void showErrorPanel() {
        errorPanel.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);
    }

    private void hideErrorPanel() {
        errorPanel.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
    }

    private String summarizeBaseUrl() {
        String baseUrl = getConfiguredBaseUrl();
        if (TextUtils.isEmpty(baseUrl)) {
            return getString(R.string.not_configured);
        }
        Uri uri = Uri.parse(baseUrl);
        String host = uri.getHost();
        if (TextUtils.isEmpty(host)) {
            return baseUrl;
        }
        if (uri.getPort() > 0) {
            return host + ":" + uri.getPort();
        }
        return host;
    }

    private String getConfiguredBaseUrl() {
        String stored = preferences.getString(KEY_BASE_URL, "");
        if (!TextUtils.isEmpty(normalizedBaseUrl(stored))) {
            return normalizedBaseUrl(stored);
        }
        return normalizedBaseUrl(getString(R.string.default_base_url));
    }

    private String getConfiguredWebToken() {
        String stored = preferences.getString(KEY_WEB_TOKEN, "");
        if (!TextUtils.isEmpty(stored != null ? stored.trim() : "")) {
            return stored.trim();
        }
        return getString(R.string.default_web_token).trim();
    }

    private static String extractSharedText(Intent intent) {
        if (intent == null) {
            return null;
        }
        String action = intent.getAction();
        if (!Intent.ACTION_SEND.equals(action)) {
            return null;
        }
        CharSequence text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
        if (text == null) {
            return null;
        }
        String normalized = text.toString().trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static String normalizedBaseUrl(String value) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty()) {
            return "";
        }
        if (!candidate.contains("://")) {
            candidate = "http://" + candidate;
        }
        Uri uri = Uri.parse(candidate);
        if (TextUtils.isEmpty(uri.getScheme()) || TextUtils.isEmpty(uri.getAuthority())) {
            return "";
        }

        Uri.Builder builder = uri.buildUpon().fragment(null);
        return builder.build().toString();
    }

    private static String buildLaunchUrl(String baseUrl, String token, String shareText, boolean autoSubmit) {
        Uri baseUri = Uri.parse(baseUrl);
        Uri.Builder builder = baseUri.buildUpon();
        builder.fragment(buildLaunchFragment(token, shareText, autoSubmit));
        return builder.build().toString();
    }

    private static String buildLaunchFragment(String token, String shareText, boolean autoSubmit) {
        List<String> params = new ArrayList<>();
        if (!TextUtils.isEmpty(token)) {
            params.add("token=" + Uri.encode(token));
        }
        if (!TextUtils.isEmpty(shareText)) {
            params.add("prefill=" + Uri.encode(shareText));
            if (autoSubmit) {
                params.add("auto_submit=1");
            }
        }
        return TextUtils.join("&", params);
    }
}
