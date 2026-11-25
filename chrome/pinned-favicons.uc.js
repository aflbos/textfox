(() => {
  "use strict";

  const { PrivateBrowsingUtils } = ChromeUtils.importESModule(
    "resource://gre/modules/PrivateBrowsingUtils.sys.mjs"
  );
  const browser = window.gBrowser;
  if (!browser || PrivateBrowsingUtils.isWindowPrivate(window)) return;

  const { PlacesUtils } = ChromeUtils.importESModule("resource://gre/modules/PlacesUtils.sys.mjs");
  const { getMozRemoteImageURL } = ChromeUtils.importESModule(
    "moz-src:///toolkit/modules/FaviconUtils.sys.mjs"
  );
  const tabs = browser.tabContainer;
  const pending = new WeakMap();
  const size = 32;

  function clear(tab) {
    tab.removeAttribute("textfox-hd-favicon");
    tab.style.removeProperty("--textfox-pinned-favicon");
  }

  async function update(tab) {
    const uri = tab.linkedBrowser?.currentURI;
    const source = tab.getAttribute("image") || "";
    const previous = pending.get(tab);
    const request = { uri, source };
    pending.set(tab, request);
    if (previous?.uri?.spec !== uri?.spec || previous?.source !== source) clear(tab);

    if (!tab.pinned || !(uri?.schemeIs("https") || uri?.schemeIs("http"))) return;
    if (!source.startsWith("data:") && !source.startsWith("moz-remote-image:")) return;
    if (source.startsWith("data:image/svg+xml")) return;

    try {
      const displaySize = Math.ceil(size * window.devicePixelRatio);
      const remote = source.startsWith("moz-remote-image:")
        ? new URL(source).searchParams.get("url")
        : null;
      // Keep the SVG already chosen by the page, including its light/dark variant.
      let data = remote?.startsWith("data:image/svg+xml;") ? remote : null;
      if (!data) {
        const icon = await PlacesUtils.favicons.getFaviconForPage(uri, displaySize);
        if (pending.get(tab) !== request || !tab.isConnected) return;
        const native = tab.querySelector(".tab-icon-image");
        if (!icon || icon.width < size || icon.width <= native?.naturalWidth) return;
        data = icon.dataURI.spec;
      }
      if (!data.startsWith("data:image/")) return;

      // Let Gecko re-encode cached website images outside the browser UI process.
      const safeURL = getMozRemoteImageURL(data, { size: displaySize });
      tab.style.setProperty("--textfox-pinned-favicon", `url(${CSS.escape(safeURL)})`);
      tab.setAttribute("textfox-hd-favicon", "");
    } catch {
      // Browsing history or icon decoding can be unavailable. Keep the browser's icon.
    }
  }

  function onFaviconChanged(events) {
    for (const tab of browser.tabs) {
      if (tab.pinned && events.some(event => event.url === tab.linkedBrowser.currentURI.spec)) {
        update(tab);
      }
    }
  }

  const progress = {
    onLocationChange(linkedBrowser, webProgress) {
      const tab = browser.getTabForBrowser(linkedBrowser);
      if (webProgress.isTopLevel && tab?.pinned) update(tab);
    },
  };

  tabs.addEventListener("TabPinned", event => update(event.target));
  tabs.addEventListener("TabUnpinned", event => {
    pending.delete(event.target);
    clear(event.target);
  });
  tabs.addEventListener("TabAttrModified", event => {
    if (event.target.pinned && event.detail.changed.includes("image")) update(event.target);
  });
  browser.addTabsProgressListener(progress);
  PlacesUtils.observers.addListener(["favicon-changed"], onFaviconChanged);
  window.addEventListener("unload", () => {
    browser.removeTabsProgressListener(progress);
    PlacesUtils.observers.removeListener(["favicon-changed"], onFaviconChanged);
  }, { once: true });
  for (const tab of browser.tabs) {
    if (tab.pinned) update(tab);
  }
})();
