#!/usr/bin/env python3
"""Check Textfox styles in a disposable Waterfox profile."""

from pathlib import Path
import time

from gecko_session import browser_argument, gecko_profile


ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = {
    "browser.statusbar.enabled": True,
    "browser.tabs.verticalTabs.tree.enabled": True,
    "browser.uidensity": 0,
    "sidebar.revamp": True,
    "sidebar.verticalTabs": True,
    "sidebar.visibility": "always-show",
    "ui.prefersReducedMotion": 0,
}
DARK_THEME = {
    "id": "textfox-chrome-test@local",
    "accentcolor": "#151923",
    "textcolor": "#dee3ed",
}

THEME_COLORS = """
const root = document.documentElement;
Services.obs.notifyObservers(
  { wrappedJSObject: { theme: arguments[0] } },
  "lightweight-theme-styling-update"
);
const sample = document.createElementNS("http://www.w3.org/1999/xhtml", "span");
root.append(sample);
const color = (value) => {
  sample.style.setProperty("color", value, "important");
  return getComputedStyle(sample).color;
};
const colors = {
  border: getComputedStyle(document.querySelector("#nav-bar")).borderTopColor,
  accent: color("var(--tf-accent)"),
  fallbackBorder: color(
    "color-mix(in srgb, var(--tf-bg) 70%, var(--toolbarbutton-icon-fill, currentColor) 30%)"
  ),
  iconColor: color("var(--toolbarbutton-icon-fill)"),
};
sample.remove();
return colors;
"""

SIDEBAR = """
const controller = window.SidebarController;
const host = controller?.sidebarMain;
const wrapper = host?.shadowRoot?.querySelector(".buttons-wrapper");
const actions = wrapper?.querySelector(".tools-and-extensions:not(.overflow-button)");
const container = document.getElementById("sidebar-container");
if (!actions || !container) return null;
if (arguments[0]) {
  // Capture the animated frame even if it falls between two driver requests.
  container.removeAttribute("data-textfox-observed-shrink");
  const observer = new MutationObserver(() => {
    if (!container.hasAttribute("sidebar-ongoing-animations")) return;
    container.setAttribute("data-textfox-observed-shrink", getComputedStyle(container).flexShrink);
    observer.disconnect();
  });
  observer.observe(container, { attributes: true, attributeFilter: ["sidebar-ongoing-animations"] });
  controller.handleToolbarButtonClick();
}
const treeButton = document.querySelector(
  "#vertical-tabs[tree-tabs-enabled] #waterfox-tree-newtab-action-button"
);
const title = getComputedStyle(wrapper, "::before");
return {
  expanded: host.expanded,
  background: getComputedStyle(host).backgroundColor,
  orientation: actions.getAttribute("orientation"),
  arrangement: getComputedStyle(actions).justifyContent,
  title: title.content,
  titleTop: title.marginTop,
  ongoing: container.hasAttribute("sidebar-ongoing-animations"),
  observedShrink: container.getAttribute("data-textfox-observed-shrink"),
  treeButton: treeButton && {
    display: getComputedStyle(treeButton).display,
    rounding: getComputedStyle(treeButton).borderRadius,
  },
};
"""

STATUS = """
const root = document.documentElement;
const bar = document.getElementById("status-bar");
const label = document.querySelector("#status-text > #statuspanel-label");
const tab = document.querySelector(".tabbrowser-tab[fadein]:not([pinned]) > .tab-stack");
if (!bar || !label || !tab) return null;
return {
  fullscreen: root.getAttribute("inFullscreen") === "true",
  barTitleDisplay: getComputedStyle(bar, "::before").display,
  barBorder: getComputedStyle(bar).borderTopWidth,
  barMargin: getComputedStyle(bar).marginTop,
  labelTransition: getComputedStyle(label).transitionDuration,
  tabAnimation: getComputedStyle(tab).animationName,
  reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
};
"""


def wait_for(read, condition, description):
    deadline = time.monotonic() + 5
    while True:
        result = read()
        if result is not None and condition(result):
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"{description}: {result}")
        time.sleep(0.05)


def check_colors(execute):
    execute("document.documentElement.style.setProperty('--tf-border-transition', '0s');")
    cases = [
        ("default", None, None, None),
        ("no custom colors", {}, None, None),
        ("explicit border", {"toolbar_field_border": "#365a87"}, "rgb(54, 90, 135)", None),
        ("explicit accent", {"tab_line": "#ed774a"}, None, "rgb(237, 119, 74)"),
        ("both colors", {"toolbar_field_border": "#365a87", "tab_line": "#ed774a"},
         "rgb(54, 90, 135)", "rgb(237, 119, 74)"),
        ("transparent border", {"toolbar_field_border": "transparent"}, None, None),
        ("light theme fallback", {"accentcolor": "#eff4fb", "textcolor": "#374260"}, None, None),
        ("translucent border", {"toolbar_field_border": "#365a8780"},
         "rgba(54, 90, 135, 0.5)", None),
        ("return to dark fallback", {}, None, None),
    ]
    for name, colors, border, accent in cases:
        theme = None if colors is None else {**DARK_THEME, **colors}
        result = execute(THEME_COLORS, theme)
        assert result["border"] == (border or result["fallbackBorder"]), (name, result)
        assert result["accent"] == (accent or result["iconColor"]), (name, result)
    print(f"PASS {len(cases)} toolbar border and accent combinations")


def check_sidebar(execute):
    execute(THEME_COLORS, DARK_THEME)
    execute("document.documentElement.style.setProperty('--tf-rounding', '7px');")
    before = wait_for(lambda: execute(SIDEBAR), lambda _: True, "sidebar not ready")
    if not before["expanded"]:
        execute(SIDEBAR, True)
    expanded = wait_for(
        lambda: execute(SIDEBAR),
        lambda item: item["expanded"] and item["orientation"] == "horizontal" and not item["ongoing"],
        "sidebar did not expand",
    )
    assert expanded["background"] == "rgb(21, 25, 35)", expanded
    assert expanded["arrangement"] == "space-evenly" and expanded["title"] == '"tools"', expanded
    assert expanded["treeButton"] == {"display": "flex", "rounding": "7px"}, expanded

    execute(SIDEBAR, True)
    collapsed = wait_for(
        lambda: execute(SIDEBAR),
        lambda item: not item["expanded"] and item["orientation"] == "vertical" and not item["ongoing"],
        "sidebar did not collapse",
    )
    assert collapsed["observedShrink"] == "0", collapsed
    assert collapsed["background"] == expanded["background"], collapsed
    assert collapsed["titleTop"] == "-8px", collapsed
    print("PASS sidebar layout and tree-tab control")


def check_tab_states(execute, orientation):
    result = execute("""
const selected = gBrowser.selectedTab;
const other = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
const style = (tab) => {
  const css = getComputedStyle(tab.querySelector(".tab-background"));
  return [css.borderBlockEndWidth, css.borderInlineStartWidth, css.outlineStyle];
};
const before = [style(selected), style(other)];
const otherBackground = other.querySelector(".tab-background");
otherBackground.style.setProperty("transition", "none", "important");
const background = () => getComputedStyle(otherBackground).backgroundColor;
const idleBackground = background();
InspectorUtils.addPseudoClassLock(other, ":hover");
const hovered = { selected: style(selected), other: style(other), background: background() };
InspectorUtils.removePseudoClassLock(other, ":hover");
gBrowser.selectedTab = other;
Services.focus.setFocus(other, Ci.nsIFocusManager.FLAG_BYKEY);
const after = [style(selected), style(other)];
const focus = [other.matches(":focus-visible"), document.activeElement === other];
gBrowser.selectedTab = selected;
gBrowser.removeTab(other, { animate: false });
return { before, after, focus, hovered, idleBackground };
""")
    marker = ["3px", "1px"] if orientation == "horizontal" else ["1px", "3px"]
    assert result["before"][0][:2] == marker, result
    assert result["before"][1][:2] == ["1px", "1px"], result
    assert result["hovered"]["selected"][:2] == marker, result
    assert result["hovered"]["other"][:2] == ["1px", "1px"], result
    assert result["hovered"]["background"] != result["idleBackground"], result
    assert result["focus"] == [True, True] and result["after"][1][2] == "dashed", result
    assert result["after"][0][:2] == ["1px", "1px"] and result["after"][1][:2] == marker, result
    print(f"PASS {orientation} selection marker differs from hover and keyboard focus")


def check_density(execute, *, vertical=False):
    read_sizes = """
const css = (selector) => getComputedStyle(document.querySelector(selector));
const height = (element) => element.getBoundingClientRect().height;
return {
  address: height(document.querySelector("#urlbar")),
  navbarPadding: parseFloat(css("#nav-bar").paddingTop),
  tab: height(gBrowser.selectedTab),
  font: css("#urlbar-input").fontSize,
  ...(arguments[0] && {
    sidebarMargin: parseFloat(css("#vertical-tabs").marginTop),
    statusPadding: parseFloat(css("#status-bar").paddingTop),
  }),
};
"""
    sizes = []
    for density in (0.75, 1, 1.25):
        execute("document.documentElement.style.setProperty('--tf-density', arguments[0]);", density)
        sizes.append(wait_for(
            lambda: execute(read_sizes, vertical),
            lambda size: not sizes or size["address"] > sizes[-1]["address"],
            f"address field did not resize at density {density}",
        ))
    execute("document.documentElement.style.removeProperty('--tf-density');")
    assert len({size["font"] for size in sizes}) == 1, sizes
    for key in sizes[0].keys() - {"font"}:
        assert sizes[0][key] < sizes[1][key] < sizes[2][key], (key, sizes)
    print(f"PASS compact, standard and comfortable spacing ({'vertical' if vertical else 'horizontal'})")


def check_frame_spacing(execute):
    for style in ("nova", "proton", "photon"):
        execute("""
const { WaterfoxBrowserStyle } = ChromeUtils.importESModule("resource:///modules/WaterfoxBrowserStyle.sys.mjs");
WaterfoxBrowserStyle.setStyle(arguments[0]);
""", style)
        for density in (0.75, 1, 1.25):
            top, side, title_top, title_center, sidebar_top, border_center = execute("""
document.documentElement.style.setProperty("--tf-density", arguments[0]);
const rect = id => document.getElementById(id).getBoundingClientRect();
const navbar = rect("nav-bar");
const main = rect("tabbrowser-tabbox");
const tabs = rect("vertical-tabs");
const tabFrame = document.getElementById("vertical-tabs");
const title = getComputedStyle(tabFrame, "::before");
const border = parseFloat(getComputedStyle(tabFrame).borderTopWidth);
const anchor = tabFrame.offsetParent;
const titleTop = anchor.getBoundingClientRect().top + anchor.clientTop
  + parseFloat(title.top) + parseFloat(title.marginTop);
const sidebarTop = rect("sidebar-container").top;
return [
  main.top - navbar.bottom,
  Math.max(main.left - tabs.right, tabs.left - main.right),
  titleTop,
  titleTop + parseFloat(title.height) / 2,
  sidebarTop,
  tabs.top + border / 2,
];
""", density)
            assert side > 0 and abs(top - side) < 0.1, (style, density, top, side)
            assert sidebar_top - 0.1 <= title_top, (style, density, sidebar_top, title_top)
            assert abs(title_center - border_center) < 0.1, (style, density, title_center, border_center)
    execute("document.documentElement.style.removeProperty('--tf-density');")
    print("PASS equal frame gaps and unclipped vertical tab titles in all styles and densities")


def check_expanded_pinned_grid(execute):
    execute("""
const controller = window.SidebarController;
if (!controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
for (let i = 0; i < 6; i++) {
  const tab = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
  tab.setAttribute("textfox-test-pin", "");
  gBrowser.pinTab(tab);
}
""")
    read = """
const tabs = gBrowser.tabContainer;
const pins = [...tabs.querySelectorAll("[textfox-test-pin]")];
return pins.map(tab => {
  const frame = tab.querySelector(".tab-background").getBoundingClientRect();
  const icon = tab.querySelector(".tab-icon-image").getBoundingClientRect();
  return {
    nativeGrid: tabs.isContainerVerticalPinnedGrid(tab),
    row: Math.round(tab.getBoundingClientRect().top),
    width: frame.width,
    height: frame.height,
    icon: [icon.width, icon.height],
    center: [
      frame.left + frame.width / 2 - icon.left - icon.width / 2,
      frame.top + frame.height / 2 - icon.top - icon.height / 2,
    ],
  };
});
"""
    try:
        wait_for(
            lambda: execute(read),
            lambda pins: len(pins) == 6 and all(pin["nativeGrid"] for pin in pins),
            "expanded native pinned grid",
        )
        painted_widths = execute("""
return (async () => {
  const icons = [...gBrowser.tabContainer.querySelectorAll("[textfox-test-pin] .tab-icon-image")];
  const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  const ctx = canvas.getContext("2d");
  const color = "rgb(247, 3, 223)";
  const widths = [];
  for (const [index, size] of [16, 64, 16].entries()) {
    const icon = icons[index];
    canvas.width = canvas.height = size;
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, size, size);
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
      + '<rect width="16" height="16" fill="' + color + '"/></svg>';
    icon.src = index === 2 ? "data:image/svg+xml," + encodeURIComponent(svg) : canvas.toDataURL();
    await icon.decode();
    const box = icon.getBoundingClientRect();
    canvas.width = Math.ceil(box.width) + 2;
    canvas.height = 1;
    ctx.drawWindow(window, Math.floor(box.left), Math.floor(box.top + box.height / 2),
                   canvas.width, 1, "transparent", 1);
    const pixels = ctx.getImageData(0, 0, canvas.width, 1).data;
    let painted = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i] === 247 && pixels[i + 1] === 3 && pixels[i + 2] === 223) painted++;
    }
    widths.push(painted);
  }
  return widths;
})();
""")
        assert all(abs(width - 32) <= 1 for width in painted_widths), painted_widths
        for density in (0, 1, 2):
            execute('Services.prefs.setIntPref("browser.uidensity", arguments[0]);', density)
            pins = execute(read)
            rows = [pin["row"] for pin in pins]
            assert len(rows) == 6 and rows[0] == rows[2] < rows[3] == rows[5], (density, rows)
            assert all(
                pin["nativeGrid"] and pin["width"] >= 48
                and abs(pin["width"] - pin["height"]) < 0.1
                and pin["icon"] == [32, 32]
                and all(abs(offset) < 1 for offset in pin["center"])
                for pin in pins
            ), (density, pins)
        execute('document.getElementById("vertical-tabs").style.maxInlineSize = "142px";')
        rows = [pin["row"] for pin in execute(read)]
        assert rows[0] == rows[1] < rows[2] == rows[3] < rows[4] == rows[5], rows
    finally:
        execute("""
document.getElementById("vertical-tabs").style.removeProperty("max-inline-size");
Services.prefs.setIntPref("browser.uidensity", 0);
for (const tab of gBrowser.tabContainer.querySelectorAll("[textfox-test-pin]")) {
  gBrowser.removeTab(tab, { animate: false });
}
const controller = window.SidebarController;
if (controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
""")
    wait_for(
        lambda: execute('return gBrowser.tabContainer.hasAttribute("expanded");'),
        lambda expanded: not expanded,
        "collapsed sidebar after pinned grid checks",
    )
    print("PASS expanded pinned grid has square tiles, centered icons and responsive columns")


def check_pinned_favicon_cache(execute):
    execute((ROOT / "chrome/pinned-favicons.uc.js").read_text(encoding="utf-8"))
    execute("""
const controller = window.SidebarController;
if (!controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
const tab = gBrowser.addTrustedTab("https://textfox.example/favicons", { skipAnimation: true });
tab.setAttribute("textfox-test-cache", "");
gBrowser.pinTab(tab);
""")
    tab = 'const tab = gBrowser.tabContainer.querySelector("[textfox-test-cache]");\n'
    try:
        wait_for(
            lambda: execute(tab + """
return tab.linkedBrowser.currentURI.spec === "https://textfox.example/favicons"
  && !tab.linkedBrowser.webProgress.isLoadingDocument;
"""),
            bool, "offline tab ready for favicon fixtures",
        )
        execute(tab + """
const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
canvas.width = canvas.height = 16;
canvas.getContext("2d").fillRect(0, 0, 16, 16);
gBrowser.setIcon(tab, canvas.toDataURL());
""")
        assert not execute(tab + 'return tab.hasAttribute("textfox-hd-favicon");')
        cached = execute(tab + """
return (async () => {
  const { PlacesUtils } = ChromeUtils.importESModule("resource://gre/modules/PlacesUtils.sys.mjs");
  const uri = tab.linkedBrowser.currentURI;
  await PlacesUtils.history.insert({ url: uri.spec, visits: [{ date: new Date() }] });
  const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fa05c8";
  ctx.fillRect(0, 0, 64, 64);
  await PlacesUtils.favicons.setFaviconForPage(
    uri, Services.io.newURI("https://textfox.example/icon.png"),
    Services.io.newURI(canvas.toDataURL()), 0, true
  );
  const icon = await PlacesUtils.favicons.getFaviconForPage(uri, 32);
  return [icon.width, icon.dataURI.spec];
})();
""")
        assert cached[0] >= 32, cached[0]
        wait_for(
            lambda: execute(tab + """
const icon = tab.querySelector(".tab-icon-image");
const content = getComputedStyle(icon).content;
const url = content.startsWith('url("moz-remote-image:') ? new URL(content.slice(5, -2)) : null;
return [tab.hasAttribute("textfox-hd-favicon"), url?.searchParams.get("url") === arguments[0],
        icon.getAttribute("src") !== arguments[0]];
""", cached[1]),
            lambda state: state == [True, True, True], "higher resolution favicon displayed",
        )
        wait_for(lambda: execute(tab + """
const box = tab.querySelector(".tab-icon-image").getBoundingClientRect();
const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
canvas.width = canvas.height = 1;
const ctx = canvas.getContext("2d");
ctx.drawWindow(window, Math.floor(box.x + box.width / 2), Math.floor(box.y + box.height / 2),
               1, 1, "transparent", 1);
return Array.from(ctx.getImageData(0, 0, 1, 1).data);
"""), lambda pixel: pixel == [250, 5, 200, 255], "cached favicon painted over the native icon")
        assert execute(tab + """
gBrowser.unpinTab(tab);
return !tab.hasAttribute("textfox-hd-favicon")
  && !tab.style.getPropertyValue("--textfox-pinned-favicon");
""")
    finally:
        execute(tab + """
gBrowser.removeTab(tab, { animate: false });
const controller = window.SidebarController;
if (controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
""")
    print("PASS pinned tabs use higher-resolution cached favicons and restore the native icon on unpin")


def check_collapsed_tab_frames(execute):
    pinned = execute("""
const tab = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
gBrowser.pinTab(tab);
return tab.linkedPanel;
""")
    heights = []
    for density in (0.75, 1, 1.25):
        frames = execute("""
document.documentElement.style.setProperty("--tf-density", arguments[0]);
const tabs = document.getElementById("tabbrowser-tabs");
if (tabs.hasAttribute("expanded")) return null;
const selected = gBrowser.selectedTab;
const pinned = Array.from(gBrowser.tabs).find(tab => tab.linkedPanel === arguments[1]);
return [selected, pinned].map(tab => {
  const frame = tab.querySelector(".tab-background").getBoundingClientRect();
  const icon = tab.querySelector(".tab-icon-image").getBoundingClientRect();
  return {
    square: Math.abs(frame.width - frame.height) < 0.1 && frame.width > 0,
    icon: [icon.width, icon.height],
    x: frame.left + frame.width / 2 - icon.left - icon.width / 2,
    y: frame.top + frame.height / 2 - icon.top - icon.height / 2,
    row: tab.getBoundingClientRect().height,
  };
});
""", density, pinned)
        assert frames and all(
            frame["square"] and frame["icon"] == [16, 16]
            and abs(frame["x"]) < 1 and abs(frame["y"]) < 1
            for frame in frames
        ), (density, frames)
        heights.append(frames[0]["row"])
    assert heights[0] < heights[1] < heights[2], heights
    execute("""
document.documentElement.style.removeProperty("--tf-density");
const pinned = Array.from(gBrowser.tabs).find(tab => tab.linkedPanel === arguments[0]);
gBrowser.removeTab(pinned, { animate: false });
""", pinned)
    print("PASS collapsed tab frames stay square and preserve density-dependent row spacing")


def check_compact_frame_titles(execute, *, vertical=False):
    execute("""
document.documentElement.style.setProperty("--tf-density", "0.75");
setToolbarVisibility(document.getElementById("PersonalToolbar"), true);
""")
    if vertical:
        execute("""
window.SidebarController.show("viewBookmarksSidebar");
gBrowser.getFindBar().then(bar => bar.open());
""")
    read = """
const frames = [
  ...["nav-bar", "PersonalToolbar", arguments[0] ? "vertical-tabs" : "TabsToolbar", "tabbrowser-tabbox"]
    .map(id => document.getElementById(id)),
  ...(arguments[0] ? [
    document.getElementById("sidebar-box"),
    window.SidebarController.sidebarMain?.shadowRoot?.querySelector(".buttons-wrapper"),
    document.querySelector("findbar"),
    document.getElementById("status-bar"),
  ] : []),
];
if (frames.some(frame => !frame?.getBoundingClientRect().height)) return null;
return frames.map(frame => {
  const box = frame.getBoundingClientRect();
  const style = getComputedStyle(frame);
  const title = getComputedStyle(frame, "::before");
  const anchor = style.position === "static" ? frame.offsetParent : frame;
  const origin = anchor.getBoundingClientRect().top + anchor.clientTop;
  const top = origin + parseFloat(title.top) + parseFloat(title.marginTop);
  return [title.content, top, top + parseFloat(title.height) / 2, box.top + parseFloat(style.borderTopWidth) / 2];
});
"""
    for font_size, border_width in (("14px", "2px"), ("16px", "1px")):
        execute("""
document.documentElement.style.setProperty("--tf-font-size", arguments[0]);
document.documentElement.style.setProperty("--tf-border-width", arguments[1]);
""", font_size, border_width)
        frames = wait_for(lambda: execute(read, vertical), bool, "compact frames")
        for title, top, center, border_center in frames:
            assert top >= -0.1 and abs(center - border_center) <= 1, (title, top, center, border_center)

    if vertical:
        execute("""
const primary = gBrowser.selectedTab;
const secondary = gBrowser.addTrustedTab("about:blank");
gBrowser.addTabSplitView([primary, secondary]);
gBrowser.selectedTab = secondary;
""")
        split = wait_for(
            lambda: execute("""
const panel = document.querySelector(".split-view-panel.deck-selected");
if (!panel) return null;
const title = getComputedStyle(panel, "::before");
return [
  title.content,
  Number(title.zIndex),
  Number(getComputedStyle(panel.querySelector(".browserContainer")).zIndex),
  panel.clientTop / 2 + parseFloat(title.top) + parseFloat(title.marginTop) + parseFloat(title.height) / 2,
];
"""),
            bool,
            "active split frame",
        )
        assert split[0] == '"active split"' and split[1] > split[2] and abs(split[3]) <= 1, split
    print(f"PASS compact frame titles are centered on the borders ({'vertical' if vertical else 'horizontal'})")


def check_status_and_motion(execute):
    start = wait_for(lambda: execute(STATUS), lambda _: True, "status bar or tabs not ready")
    assert start["barBorder"] == "2px" and start["barMargin"] == "6px", start
    assert start["tabAnimation"] == "tf-tab-in" and start["labelTransition"] == "0.15s", start

    execute("Services.prefs.setIntPref('ui.prefersReducedMotion', 1);")
    wait_for(
        lambda: execute(STATUS),
        lambda item: item["reduced"] and item["tabAnimation"] == "none" and item["labelTransition"] == "0s",
        "reduced-motion styles did not take effect",
    )
    print("PASS reduced-motion preference disables the tab and status animations")

    execute("window.fullScreen = true;")
    full = wait_for(lambda: execute(STATUS), lambda item: item["fullscreen"], "fullscreen")
    assert full["barBorder"] == "0px" and full["barMargin"] == "0px", full
    assert full["barTitleDisplay"] == "none", full
    print("PASS fullscreen removes the status bar frame and title")


def check_waterfox_appearance(execute, orientation):
    for style, palette in (("nova", "pine"), ("proton", "sun"), ("photon", "dusk")):
        for mode in ("light", "dark"):
            execute("""
const { WaterfoxBrowserStyle } = ChromeUtils.importESModule("resource:///modules/WaterfoxBrowserStyle.sys.mjs");
const { WaterfoxThemeColors } = ChromeUtils.importESModule("resource:///modules/WaterfoxThemeColors.sys.mjs");
WaterfoxBrowserStyle.setStyle(arguments[0]);
WaterfoxThemeColors.setColor(arguments[1]);
WaterfoxThemeColors.setMode(arguments[2]);
""", style, palette, mode)
            appearance = wait_for(
                lambda: execute("""
const root = document.documentElement;
const css = getComputedStyle(root);
const content = getComputedStyle(document.querySelector(".browserContainer"));
const tab = getComputedStyle(gBrowser.selectedTab.querySelector(".tab-background"));
return {
  nova: Services.prefs.getBoolPref("browser.nova.enabled"),
  background: content.backgroundColor,
  palette: css.getPropertyValue("--lwt-accent-color").trim(),
  marker: arguments[0] === "vertical" ? tab.borderInlineStartWidth : tab.borderBlockEndWidth,
};
""", orientation),
                lambda item: item["palette"] and item["background"] == item["palette"],
                f"{style} with {palette} in {mode} mode",
            )
            assert appearance["nova"] == (style == "nova"), appearance
            assert appearance["marker"] == "3px", appearance
            if mode == "light":
                light = appearance["background"]
            else:
                assert light != appearance["background"], appearance

        execute("""
document.documentElement.style.setProperty("--tf-rounding", "9px");
document.getElementById("contentAreaContextMenu").openPopupAtScreen(120, 120, true);
""")
        popup = wait_for(
            lambda: execute("""
const popup = document.getElementById("contentAreaContextMenu");
const frame = popup.shadowRoot.querySelector('[part~="content"]');
return {
  state: popup.state,
  appearance: getComputedStyle(popup).appearance,
  radius: getComputedStyle(frame).borderRadius,
  itemRadius: getComputedStyle(popup.querySelector("menuitem")).borderRadius,
};
"""),
            lambda item: item["state"] == "open",
            f"{style} context menu did not open",
        )
        assert popup == {"state": "open", "appearance": "none", "radius": "0px", "itemRadius": "0px"}, popup
        execute("""
document.getElementById("contentAreaContextMenu").hidePopup();
document.documentElement.style.removeProperty("--tf-rounding");
""")
    print(f"PASS Nova, Proton and Photon palettes and square context menus ({orientation})")


def check_native_density(execute):
    for preference, attribute, scale in ((1, "compact", "0.75"), (2, "touch", "1.25"), (0, None, "1")):
        execute("Services.prefs.setIntPref('browser.uidensity', arguments[0]);", preference)
        wait_for(
            lambda: execute("""
const root = document.documentElement;
return [root.getAttribute("uidensity"), getComputedStyle(root).getPropertyValue("--tf-density").trim()];
"""),
            lambda result: result == [attribute, scale],
            f"browser density {preference}",
        )
    print("PASS native Compact, Touch and Normal density settings")


def check_sine_preferences(execute):
    execute("""
Services.prefs.setIntPref("browser.uidensity", 2);
Services.prefs.setStringPref("textfox.sine.density", "compact");
Services.prefs.setStringPref("textfox.sine.border", "thick");
Services.prefs.setBoolPref("textfox.sine.hideTitles", true);
Services.prefs.setStringPref("textfox.sine.fontSize", "large");
Services.prefs.setStringPref("textfox.sine.rounding", "rounded");
Services.prefs.setBoolPref("textfox.sine.disableMotion", true);
Services.prefs.setBoolPref("textfox.sine.hideSidebarTools", true);
""")

    def read_styles():
        return execute("""
const navbar = document.querySelector("#nav-bar");
const toolbar = getComputedStyle(navbar);
const sidebarTools = window.SidebarController.sidebarMain?.shadowRoot?.querySelector(".buttons-wrapper");
if (!sidebarTools) return null;
return [
  toolbar.paddingTop,
  toolbar.borderTopWidth,
  getComputedStyle(navbar, "::before").display,
  getComputedStyle(document.getElementById("urlbar-input")).fontSize,
  toolbar.borderRadius,
  toolbar.transitionDuration,
  getComputedStyle(sidebarTools).display,
];
""")

    enabled = ["3px", "3px", "none", "16px", "8px", "0s", "none"]
    wait_for(read_styles, lambda styles: styles == enabled, "Sine preferences")
    execute("""
Services.prefs.setStringPref("textfox.sine.density", "browser");
Services.prefs.setStringPref("textfox.sine.border", "theme");
Services.prefs.setBoolPref("textfox.sine.hideTitles", false);
Services.prefs.setStringPref("textfox.sine.fontSize", "theme");
Services.prefs.setStringPref("textfox.sine.rounding", "theme");
Services.prefs.setBoolPref("textfox.sine.disableMotion", false);
Services.prefs.setBoolPref("textfox.sine.hideSidebarTools", false);
""")
    defaults = ["5px", "2px", "flex", "14px", "0px", "0.2s", "flex"]
    wait_for(read_styles, lambda styles: styles == defaults, "Sine defaults")
    print("PASS Sine appearance preferences override and restore theme defaults")


def check_sine_urlbar_and_status(execute):
    styles = """
const style = (id) => getComputedStyle(document.getElementById(id));
return {
  shield: style("tracking-protection-icon-container").display,
  container: style("userContext-icons").display,
  bookmark: style("star-button-box").display,
  translation: style("translations-button").display,
  identity: style("identity-box").display,
  status: style("status-bar").display,
  statusText: style("statuspanel-label").display,
  link: document.getElementById("statuspanel-label").value,
  statusBorder: style("status-bar").borderTopWidth,
  statusTitle: getComputedStyle(document.getElementById("status-bar"), "::before").display,
};
"""
    execute("""
gBrowser.selectedBrowser.loadURI(Services.io.newURI("data:text/html,<title>Address controls</title>"), {
  triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
});
""")
    wait_for(
        lambda: execute('return gURLBar.getAttribute("pageproxystate");'),
        lambda state: state == "valid",
        "address bar did not reach a valid page",
    )
    execute("""
// Model an available container indicator. Translation stays unavailable.
document.getElementById("userContext-icons").hidden = false;
XULBrowserWindow.setOverLink("https://example.invalid/status");
""")
    before = wait_for(
        lambda: execute(styles),
        lambda css: css["link"] == "https://example.invalid/status",
        "status bar did not show the hovered link",
    )
    assert before["container"] != "none" and before["bookmark"] == "none", before
    assert before["translation"] == "none" and before["statusBorder"] == "2px", before
    execute("""
Services.prefs.setBoolPref("textfox.sine.showUrlbarActions", true);
Services.prefs.setBoolPref("textfox.sine.hideUrlbarIndicators", true);
Services.prefs.setBoolPref("textfox.sine.discreetStatusBar", true);
""")
    after = wait_for(
        lambda: execute(styles),
        lambda css: css["bookmark"] != "none" and css["container"] == "none"
        and css["shield"] == "none" and css["statusBorder"] == "0px",
        "address bar and status preferences",
    )
    assert after["translation"] == "none" and after["identity"] == before["identity"], after
    assert after["statusTitle"] == "none", after
    assert after["status"] == before["status"] and after["statusText"] == before["statusText"], after
    assert after["link"] == before["link"], after
    execute("""
Services.prefs.clearUserPref("textfox.sine.showUrlbarActions");
Services.prefs.clearUserPref("textfox.sine.hideUrlbarIndicators");
Services.prefs.clearUserPref("textfox.sine.discreetStatusBar");
""")
    wait_for(lambda: execute(styles), lambda css: css == before, "address bar and status defaults")
    print("PASS separate address bar indicators and actions, and borderless status bar")


def check_sine_area_titles(execute, *, vertical=False):
    def read():
        return execute("""
const tabs = document.getElementById(arguments[0] ? "vertical-tabs" : "TabsToolbar");
const tools = window.SidebarController.sidebarMain?.shadowRoot?.querySelector(".buttons-wrapper");
const main = document.getElementById("tabbrowser-tabbox");
const status = document.getElementById("status-bar");
return [tabs, tools, main, status].map(element => element && getComputedStyle(element, "::before").display);
""", vertical)

    before = wait_for(read, lambda titles: titles[0:3] == ["flex"] * 3, "area titles before changes")
    for index, pref in enumerate(("hideTabsTitle", "hideSidebarTitles", "hideMainTitle", "hideStatusTitle")):
        if before[index] is None:
            continue
        expected = before.copy()
        expected[index] = "none"
        name = f"textfox.sine.{pref}"
        execute("Services.prefs.setBoolPref(arguments[0], true);", name)
        wait_for(read, lambda titles: titles == expected, pref)
        execute("Services.prefs.clearUserPref(arguments[0]);", name)
        wait_for(read, lambda titles: titles == before, f"restore {pref}")
    print(f"PASS independent Sine titles ({'vertical' if vertical else 'horizontal'})")


def check_sine_tree_guides(execute):
    toggle = "window.SidebarController.handleToolbarButtonClick();"
    expanded = 'return document.getElementById("tabbrowser-tabs").hasAttribute("expanded");'
    if not execute(expanded):
        execute(toggle)
    wait_for(
        lambda: execute(expanded) and execute(
            'return !document.getElementById("sidebar-container").hasAttribute("sidebar-ongoing-animations");'
        ),
        bool, "expanded vertical tabs at rest",
    )
    assert execute("""
const { TreeTabsService } = ChromeUtils.importESModule("resource:///modules/TreeTabsService.sys.mjs");
const [parent, child, grandchild, sibling] = [true, true, false, false].map(createLazyBrowser =>
  gBrowser.addTrustedTab("about:blank", { skipAnimation: true, createLazyBrowser })
);
window.textfoxExpandedGuides = { parent, child, grandchild, sibling };
return !parent.linkedPanel && !child.linkedPanel &&
  TreeTabsService.attachTab(child, parent) && TreeTabsService.attachTab(grandchild, child)
  && TreeTabsService.attachTab(sibling, parent);
""")
    read = """
const { parent, child, grandchild } = window.textfoxExpandedGuides;
if (!grandchild.hasAttribute("textfox-tree-line")) return null;
const rootLine = getComputedStyle(parent, "::before");
const nestedLine = getComputedStyle(grandchild, "::before");
const root = parent.getBoundingClientRect();
const nested = grandchild.getBoundingClientRect();
const track = Math.floor(root.left + parseFloat(rootLine.backgroundPositionX));
const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
canvas.width = 7;
const ctx = canvas.getContext("2d");
const measure = (start, height) => {
  canvas.height = height;
  ctx.drawWindow(window, track - 2, start, 7, height, "transparent", 1);
  const pixels = ctx.getImageData(0, 0, 7, height).data;
  return Math.min(...Array.from({ length: height }, (_, row) => {
    const offset = row * 28;
    return Math.max(...[1, 2, 3, 4].map(x => Math.abs(pixels[offset + x * 4] - pixels[offset])));
  }));
};
const frame = parent.querySelector(".tab-background").getBoundingClientRect();
const nestedFrame = grandchild.querySelector(".tab-background").getBoundingClientRect();
const innerTrack = nested.left + parseFloat(nestedLine.insetInlineStart)
  + parseFloat(nestedLine.backgroundPositionX.split(",")[1]);
const frameEdge = Math.round(frame.bottom) - 1;
const nextRow = Math.floor(child.getBoundingClientRect().top);
return {
  color: rootLine.color, content: rootLine.content,
  indent: getComputedStyle(child).marginInlineStart,
  nestedTracks: nestedLine.backgroundImage.split("linear-gradient").length - 1,
  paintedTrack: measure(Math.floor(nested.top) + 5, 1),
  paintedJoin: measure(frameEdge, Math.max(1, nextRow - frameEdge + 3)),
  frameClearance: [frame.left - track, nestedFrame.left - innerTrack],
  parentsUnloaded: !parent.linkedPanel && !child.linkedPanel,
};
"""
    try:
        neutral = wait_for(
            lambda: execute(read),
            lambda style: style["indent"] != "0px" and style["paintedTrack"] >= 35,
            "expanded guide paints through the gutter of a nested tab",
        )
        assert neutral["nestedTracks"] == 3 and neutral["paintedJoin"] >= 25, neutral
        assert all(distance is not None and distance > 1 for distance in neutral["frameClearance"]), neutral
        assert neutral["parentsUnloaded"], neutral
        execute('Services.prefs.setStringPref("textfox.sine.treeGuides", "accent");')
        accent = wait_for(
            lambda: execute(read), lambda style: style["color"] != neutral["color"],
            "accented continuous guide",
        )
        assert accent["indent"] == neutral["indent"] and accent["paintedTrack"] >= 35, accent
        execute('Services.prefs.setIntPref("browser.tabs.verticalTabs.tree.indentPx", 24);')
        wider = wait_for(
            lambda: execute(read),
            lambda style: style["indent"] == "24px" and style["paintedTrack"] >= 35,
            "guides follow a changed native indent",
        )
        assert wider["nestedTracks"] == neutral["nestedTracks"], wider
        execute('Services.prefs.setStringPref("textfox.sine.treeGuides", "hidden");')
        hidden = wait_for(
            lambda: execute(read), lambda style: style["content"] == "none",
            "hidden expanded guide",
        )
        assert hidden["indent"] == wider["indent"], hidden
        execute(toggle)
        wait_for(lambda: execute(expanded), lambda value: not value, "collapsed vertical tabs")
        wait_for(
            lambda: execute(read), lambda style: style["content"] != "none",
            "expanded-only preference leaves the collapsed guides visible",
        )
    finally:
        execute("""
Services.prefs.clearUserPref("textfox.sine.treeGuides");
Services.prefs.clearUserPref("browser.tabs.verticalTabs.tree.indentPx");
const { parent, child, grandchild, sibling } = window.textfoxExpandedGuides;
for (const tab of [grandchild, child, sibling, parent]) gBrowser.removeTab(tab, { animate: false });
delete window.textfoxExpandedGuides;
""")
    print("PASS expanded continuous guides follow native indentation and Sine appearance options")


def check_sine_area_colors(execute):
    popup = "document.getElementById('contentAreaContextMenu')"
    execute(f"{popup}.openPopupAtScreen(120, 120, true);")
    wait_for(lambda: execute(f"return {popup}.state;"), lambda state: state == "open", "context menu")
    read = """
const paint = (background, foreground = background) =>
  [getComputedStyle(background).backgroundColor, getComputedStyle(foreground).color];
const menu = document.getElementById("contentAreaContextMenu").shadowRoot.querySelector('[part~="content"]');
return {
  menu: paint(menu),
  sidebar: paint(window.SidebarController.sidebarMain),
  statusbar: paint(document.getElementById("browser-bottombox"), document.getElementById("status-bar")),
};
"""
    theme = {
        **DARK_THEME,
        "popup": "#443448",
        "popup_text": "#fff8ed",
        "sidebar": "#233c32",
        "sidebar_text": "#d5f7e8",
        "toolbarColor": "#233247",
        "toolbar_text": "#fff3ff",
    }
    execute(THEME_COLORS, theme)
    baseline = execute(read)
    assert all(paint[0] == "rgb(21, 25, 35)" for paint in baseline.values()), baseline
    expected = {
        "menu": ["rgb(68, 52, 72)", "rgb(255, 248, 237)"],
        "sidebar": ["rgb(35, 60, 50)", "rgb(213, 247, 232)"],
        "statusbar": ["rgb(35, 50, 71)", "rgb(255, 243, 255)"],
    }
    current = baseline.copy()
    for area, colors in expected.items():
        execute('Services.prefs.setStringPref("textfox.sine." + arguments[0] + "Color", "active");', area)
        current[area] = colors
        wait_for(lambda: execute(read), lambda colors: colors == current, f"theme colors for {area}")
    execute(THEME_COLORS, {**theme, "sidebar": "#264639"})
    expected["sidebar"][0] = "rgb(38, 70, 57)"
    wait_for(lambda: execute(read), lambda colors: colors == expected, "live color update")

    execute("""
for (const area of ["menu", "sidebar", "statusbar"]) {
  Services.prefs.setStringPref("textfox.sine." + area + "Color", "neutral");
}
""")
    neutral = wait_for(
        lambda: execute(read),
        lambda colors: all(colors[area] != expected[area] for area in expected),
        "neutral area colors",
    )
    execute(THEME_COLORS, {**theme, "sidebar": "#32473d", "popup": "#442a40", "toolbarColor": "#26364b"})
    assert execute(read) == neutral, neutral
    execute(f"""
{popup}.hidePopup();
for (const area of ["menu", "sidebar", "statusbar"]) {{
  Services.prefs.clearUserPref("textfox.sine." + area + "Color");
}}
""")
    print("PASS independent active and neutral colors for menus, sidebar and status bar")


def check_tab_hover_preview(execute):
    execute("""
const preview = document.getElementById("tab-preview-panel");
preview.hidden = false;
preview.openPopupAtScreen(140, 120, false);
""")
    wait_for(
        lambda: execute('return document.getElementById("tab-preview-panel").state;'),
        lambda state: state == "open",
        "tab preview panel",
    )
    sizes = execute("""
const { PageWireframes } = ChromeUtils.importESModule("resource:///modules/sessionstore/PageWireframes.sys.mjs");
const container = document.querySelector("#tab-preview-panel .tab-preview-thumbnail-container");
container.classList.remove("hide-thumbnail");
const measure = child => {
  container.replaceChildren(child);
  return {
    container: container.getBoundingClientRect().height,
    image: child.getBoundingClientRect().height,
    width: child.getBoundingClientRect().width,
  };
};
const wireframe = height => PageWireframes.getWireframeElement({
  canvasBackground: 0xff000000,
  rects: [{ x: 0, y: 0, width: 264, height, color: 0xffffffff }],
}, document);
const tall = measure(wireframe(750));
const short = measure(wireframe(110));
const canvas = document.createElement("canvas");
canvas.width = 280;
canvas.height = 140;
const snapshot = measure(canvas);
document.getElementById("tab-preview-panel").hidePopup();
return { tall, short, snapshot };
""")
    assert 0 < sizes["tall"]["container"] <= 148 < sizes["tall"]["image"], sizes
    assert sizes["short"]["image"] == sizes["short"]["container"] == 110, sizes
    assert 120 <= sizes["snapshot"]["container"] <= 148, sizes
    assert all(image["width"] == 264 for image in sizes.values()), sizes
    print("PASS tall tab wireframes are cropped and normal previews retain their size")


def check_tab_drop_position(execute, orientation):
    execute((ROOT / "chrome/tab-drop-position.uc.js").read_text(encoding="utf-8"))
    started = execute("""
const first = gBrowser.selectedTab;
const second = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
const third = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
const transfer = new DataTransfer();
const eventAt = (type, tab, offset, shiftKey = false) => {
  const r = tab.getBoundingClientRect();
  const x = Math.round(r.left + r.width * offset);
  const y = Math.round(r.top + r.height * offset);
  return new DragEvent(type, {
    bubbles: true, cancelable: true, dataTransfer: transfer, clientX: x, clientY: y, shiftKey,
    screenX: window.mozInnerScreenX + x, screenY: window.mozInnerScreenY + y,
  });
};
first.dispatchEvent(eventAt("dragstart", first, 0.9));
transfer.dropEffect = "move";
const centeredOver = eventAt("dragover", second, 0.55);
second.dispatchEvent(centeredOver);
window.textfoxTestDrag = { first, second, third, eventAt, centeredOver };
return gBrowser.tabContainer.hasAttribute("movingtab");
""")
    assert started, orientation
    wait_for(lambda: execute("""
const { first, centeredOver } = window.textfoxTestDrag;
const box = first.getBoundingClientRect();
return arguments[0] === "vertical"
  ? centeredOver.clientY - (box.top + box.height / 2)
  : centeredOver.clientX - (box.left + box.width / 2);
""", orientation), lambda offset: abs(offset) < 1, f"centered {orientation} drag")
    execute("""
const { third, eventAt } = window.textfoxTestDrag;
third.dispatchEvent(eventAt("dragover", third, 0.9));
""")
    result = wait_for(
        lambda: execute("""
const indicator = document.getElementById("textfox-tab-drop-position");
if (indicator.hidden) return null;
const drag = window.textfoxTestDrag.first._dragData;
const target = drag.dropElement.getBoundingClientRect();
const line = indicator.getBoundingClientRect();
const vertical = indicator.dataset.axis === "vertical";
return {
  axis: indicator.dataset.axis,
  thickness: vertical ? line.height : line.width,
  edge: vertical ? line.top + line.height / 2 : line.left + line.width / 2,
  expected: vertical
    ? (drag.dropBefore ? target.top : target.bottom)
    : (drag.dropBefore ? target.left : target.right),
};
"""),
        lambda marker: abs(marker["edge"] - marker["expected"]) < 1,
        f"native {orientation} drag indicator",
    )
    assert result["axis"] == orientation and result["thickness"] == 3, result
    assert abs(result["edge"] - result["expected"]) < 1, result
    wait_for(lambda: execute("""
const indicator = document.getElementById("textfox-tab-drop-position");
if (indicator.style.maskImage.includes("transparent")) return true;
const frame = window.textfoxTestDrag.first.querySelector(".tab-background");
frame.style.removeProperty("translate");
const line = indicator.getBoundingClientRect();
const box = frame.getBoundingClientRect();
const vertical = indicator.dataset.axis === "vertical";
const delta = vertical ? line.top + line.height / 2 - box.top - box.height / 2
  : line.left + line.width / 2 - box.left - box.width / 2;
frame.style.translate = vertical ? `0 ${delta}px` : `${delta}px 0`;
return false;
"""), bool, f"{orientation} drop indicator behind the dragged tab")
    execute('window.textfoxTestDrag.first.querySelector(".tab-background").style.removeProperty("translate");')
    if orientation == "vertical":
        assert execute("""
const { first, third, eventAt } = window.textfoxTestDrag;
const transfer = eventAt("dragover", third, 0.5).dataTransfer;
const tree = window.TreeTabsDnD;
const row = tree._getRowBounds(third);
const x = Math.round(third.getBoundingClientRect().left + 10);
return [[0.2, true], [0.28, true], [0.5, false], [0.5, true], [0.72, true], [0.8, true]]
  .map(([fraction, shiftKey]) => {
  const y = row.top + row.height * fraction;
  const event = new DragEvent("dragover", {
    bubbles: true, cancelable: true, dataTransfer: transfer, clientX: x, clientY: y, shiftKey,
    screenX: window.mozInnerScreenX + x, screenY: window.mozInnerScreenY + y,
  });
  return tree.getAttachTarget(gBrowser.tabContainer, event, first) === third;
});
""") == [False, True, False, True, True, False], "Shift enables the full native center zone"
        execute("""
const drag = window.textfoxTestDrag;
const hover = drag.eventAt("dragover", drag.third, 0.5);
const row = window.TreeTabsDnD._getRowBounds(drag.third);
const y = Math.round(row.top + row.height / 2);
const eventData = {
  bubbles: true, cancelable: true, dataTransfer: hover.dataTransfer,
  clientX: hover.clientX, clientY: y, screenX: hover.screenX, screenY: window.mozInnerScreenY + y,
};
drag.third.dispatchEvent(new DragEvent("dragover", eventData));
drag.third.dispatchEvent(new DragEvent("dragover", { ...eventData, shiftKey: true }));
drag.childTarget = gBrowser.tabContainer.querySelector('[data-tree-drop-target="child"]');
drag.childDrop = new DragEvent("drop", { ...eventData, shiftKey: true });
""")
        child = wait_for(
            lambda: execute("""
const target = window.textfoxTestDrag.childTarget;
return target?.dataset.treeDropTarget === "child" &&
  document.getElementById("textfox-tab-drop-position").hidden
  && getComputedStyle(target).outlineStyle;
"""),
            bool,
            "child drop outline",
        )
        assert child == "dashed", child
    execute("""
const { third, eventAt, childDrop } = window.textfoxTestDrag;
third.dispatchEvent(childDrop ?? eventAt("drop", third, 0.9));
""", orientation)
    wait_for(
        lambda: execute("""
const { first, third, childTarget } = window.textfoxTestDrag;
return arguments[0] === "vertical"
  ? first.dataset.treeParent === childTarget.linkedPanel
  : first._tPos > third._tPos;
""", orientation),
        bool,
        f"native {orientation} drop placement",
    )
    execute("""
const { second, third } = window.textfoxTestDrag;
gBrowser.tabContainer.tabDragAndDrop.finishAnimateTabMove();
gBrowser.removeTab(second, { animate: false });
gBrowser.removeTab(third, { animate: false });
delete window.textfoxTestDrag;
""")
    assert execute('return document.getElementById("textfox-tab-drop-position").hidden;')
    print(f"PASS {orientation} drag stays centered, highlights the native drop edge and clears on drop")


def check_tab_move_menu(execute, orientation):
    execute((ROOT / "chrome/tab-move-menu.uc.js").read_text(encoding="utf-8"))
    state = execute("""
const selected = gBrowser.selectedTab;
const context = window.TabContextMenu;
const originalTab = context.contextTab;
const originalMultiselected = context.multiselected;
const menu = document.getElementById("moveTabOptionsMenu");
const back = document.getElementById("textfox-move-tab-back");
const forward = document.getElementById("textfox-move-tab-forward");
const attach = document.getElementById("textfox-attach-tab");
const attachPopup = attach.firstElementChild;
const openFor = (tab, multiselected = false) => {
  context.contextTab = tab;
  context.multiselected = multiselected;
  menu.dispatchEvent(new Event("popupshowing", { bubbles: true }));
  return [back.disabled, forward.disabled];
};
const move = item => item.dispatchEvent(new Event("command", { bubbles: true }));
const pressMoveKey = direction => {
  const input = Cc["@mozilla.org/text-input-processor;1"].createInstance(Ci.nsITextInputProcessor);
  if (!input.beginInputTransactionForTests(window)) throw new Error("Keyboard unavailable");
  const key = (name, code, keyCode) => new KeyboardEvent("keydown", { key: name, code, keyCode });
  const ctrl = key("Control", "ControlLeft", 17);
  const shift = key("Shift", "ShiftLeft", 16);
  const page = direction < 0 ? key("PageUp", "PageUp", 33) : key("PageDown", "PageDown", 34);
  const flags = Ci.nsITextInputProcessor.KEY_NON_PRINTABLE_KEY;
  input.keydown(ctrl, flags);
  input.keydown(shift, flags);
  try {
    input.keydown(page, flags);
    input.keyup(page, flags);
  } finally {
    input.keyup(shift, flags);
    input.keyup(ctrl, flags);
  }
};
const vertical = arguments[0] === "vertical";
const [root, child, sibling, otherRoot, pin, otherPin] = Array.from({ length: 6 }, () =>
  gBrowser.addTrustedTab("about:blank", { skipAnimation: true })
);
try {
  gBrowser.pinTab(pin);
  gBrowser.pinTab(otherPin);
  if (vertical) {
    gBrowser.TreeTabsService.attachTab(child, root);
    gBrowser.TreeTabsService.attachTab(sibling, root);
  }

  const pinnedEdge = openFor(pin);
  const pinnedCannotAttach = attach.disabled;
  move(back);
  if (pin._tPos !== 0) throw new Error("A disabled command moved the first pinned tab");
  move(forward);
  const pinsMoved = pin._tPos === 1 && otherPin._tPos === 0 && pin.pinned && otherPin.pinned;
  const multiEdge = openFor(otherRoot, true);
  const ordinaryEdge = openFor(otherRoot);
  const tabLabel = back.getAttribute("label");
  move(back);
  const reordered = vertical ? otherRoot._tPos < root._tPos : otherRoot._tPos + 1 === sibling._tPos;

  let childrenReordered = true;
  if (vertical) {
    const service = gBrowser.TreeTabsService;
    const keptBranch = service.getParent(child) === root && service.getParent(sibling) === root
      && child._tPos === root._tPos + 1 && sibling._tPos === child._tPos + 1;
    const childEdge = openFor(child);
    move(forward);
    childrenReordered = keptBranch && childEdge[0] && !childEdge[1]
      && service.getChildren(root)[1] === child && child._tPos === sibling._tPos + 1;
  }
  const menuKeptSelection = selected === gBrowser.selectedTab;
  // Leave the context menu pointed at another tab to distinguish both entry points.
  const active = vertical ? child : otherRoot;
  openFor(root);
  gBrowser.selectedTab = active;
  gURLBar.focus();
  const start = active._tPos;
  const firstDirection = vertical ? -1 : 1;
  pressMoveKey(firstDirection);
  const moved = active._tPos === start + firstDirection;
  pressMoveKey(firstDirection);
  const stayedAtEdge = active._tPos === start + firstDirection;
  pressMoveKey(-firstDirection);
  const movedBack = active._tPos === start && active === gBrowser.selectedTab;
  let attachment = attach.hidden;
  if (vertical) {
    root.setAttribute("label", "Textfox root fixture");
    child.setAttribute("label", "Textfox child fixture");
    openFor(root);
    attachPopup.dispatchEvent(new Event("popupshowing", { bubbles: true }));
    const excludesDescendants = ![...attachPopup.children].some(
      item => item.getAttribute("label") === child.label
    );
    openFor(otherRoot);
    attachPopup.dispatchEvent(new Event("popupshowing", { bubbles: true }));
    const target = [...attachPopup.children].find(item => item.getAttribute("label") === root.label);
    if (target) move(target);
    attachment = pinnedCannotAttach && !attach.hidden && excludesDescendants && target &&
      gBrowser.TreeTabsService.getParent(otherRoot) === root && otherRoot._tPos > child._tPos
      && gBrowser.selectedTab === active;
  }
  return {
    pinnedEdge, pinsMoved, multiEdge, ordinaryEdge, tabLabel, reordered, childrenReordered,
    selected: menuKeptSelection,
    shortcuts: [back.getAttribute("acceltext"), forward.getAttribute("acceltext")],
    keyboard: moved && stayedAtEdge && movedBack
      && (!vertical || gBrowser.TreeTabsService.getParent(active) === root),
    attachment,
    registered: back.parentNode === menu && forward.parentNode === menu,
  };
} finally {
  context.contextTab = originalTab;
  context.multiselected = originalMultiselected;
  gBrowser.selectedTab = selected;
  for (const tab of [child, sibling, root, otherRoot, pin, otherPin]) {
    gBrowser.removeTab(tab, { animate: false });
  }
}
""", orientation)
    assert state["registered"] and state["selected"] and state["tabLabel"], state
    assert state["pinnedEdge"] == [True, False] and state["pinsMoved"], state
    assert state["multiEdge"] == [True, True] and state["ordinaryEdge"] == [False, True], state
    assert state["reordered"] and state["childrenReordered"], state
    assert all(state["shortcuts"]) and state["keyboard"] and state["attachment"], state
    print(f"PASS {orientation} menu and native keyboard shortcuts reorder the intended tab")


def check_shift_drop_requires_parent(execute):
    state = execute("""
return (async () => {
const source = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
const target = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
const transfer = new DataTransfer();
const eventAt = (type, tab, fraction, shiftKey = true) => {
  const row = window.TreeTabsDnD._getRowBounds(tab);
  const x = Math.round(tab.getBoundingClientRect().left + 10);
  const y = Math.round(row.top + row.height * fraction);
  return new DragEvent(type, {
    bubbles: true, cancelable: true, dataTransfer: transfer, shiftKey, clientX: x, clientY: y,
    screenX: window.mozInnerScreenX + x, screenY: window.mozInnerScreenY + y,
  });
};
try {
  const original = source._tPos;
  source.dispatchEvent(eventAt("dragstart", source, 0.5, false));
  transfer.dropEffect = "move";
  target.dispatchEvent(eventAt("dragover", target, 0.9));
  await new Promise(resolve => requestAnimationFrame(resolve));
  const lineHidden = document.getElementById("textfox-tab-drop-position").hidden;
  const drop = eventAt("drop", target, 0.9);
  target.dispatchEvent(drop);
  const canceled = drop.defaultPrevented && source._tPos === original
    && !gBrowser.TreeTabsService.getParent(source);
  transfer.dropEffect = "none";
  source.dispatchEvent(eventAt("dragend", source, 0.5));
  return [lineHidden, canceled, !source._dragData, source.isConnected];
} finally {
  gBrowser.removeTab(source, { animate: false });
  gBrowser.removeTab(target, { animate: false });
}
})();
""")
    assert state == [True, True, True, True], state
    print("PASS Shift drop outside the attachment zone cancels without moving the tab")


def check_collapsed_tree_cues(execute):
    execute((ROOT / "chrome/tab-move-menu.uc.js").read_text(encoding="utf-8"))
    state = execute("""
return (async () => {
const controller = window.SidebarController;
const tabs = gBrowser.tabContainer;
const wasExpanded = controller.sidebarMain.expanded;
if (wasExpanded) controller.handleToolbarButtonClick();
const [root, child, grandchild, sibling, plain] = [true, true, false, false, false].map(createLazyBrowser =>
  gBrowser.addTrustedTab("about:blank", { skipAnimation: true, createLazyBrowser })
);
const service = gBrowser.TreeTabsService;
const chromeStyle = document.documentElement.style;
const originalAccent = chromeStyle.getPropertyValue("--tf-accent");
const originalPriority = chromeStyle.getPropertyPriority("--tf-accent");
try {
  service.attachTab(child, root);
  service.attachTab(grandchild, child);
  service.attachTab(sibling, root);
  const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve));
  await nextFrame();
  await nextFrame();
  const arrow = root.querySelector(".tab-tree-disclosure");
  const guide = tab => getComputedStyle(tab.querySelector(".tab-stack"), "::before");
  const counter = root.querySelector(".tab-content");
  const showTree = [getComputedStyle(arrow).display, arrow.getAttribute("aria-expanded"),
    guide(root).insetInlineStart, guide(child).insetInlineStart,
    guide(grandchild).insetInlineStart, guide(plain).content];
  const lines = [root, child, grandchild, sibling, plain].map(tab => {
    const style = getComputedStyle(tab, "::before");
    return [style.backgroundPosition, style.backgroundSize];
  });
  chromeStyle.setProperty("--tf-accent", "var(--tf-bg)", "important");
  const rect = root.getBoundingClientRect();
  const canvas = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  canvas.width = 7;
  canvas.height = 1;
  const ctx = canvas.getContext("2d");
  ctx.drawWindow(window, Math.floor(rect.left), Math.floor(rect.bottom) - 5,
                 canvas.width, 1, "transparent", 1);
  const pixels = ctx.getImageData(0, 0, canvas.width, 1).data;
  const background = pixels.slice(24, 27);
  const contrast = Math.max(...[1, 2, 3, 4].map(x =>
    Math.max(...background.map((value, channel) => Math.abs(value - pixels[x * 4 + channel])))
  ));
  const matchingGuideColors = getComputedStyle(root, "::before").color === guide(child).borderBlockEndColor;

  arrow.click();
  await nextFrame();
  await nextFrame();
  const collapsed = [arrow.getAttribute("aria-expanded"), child.hasAttribute("data-tree-hidden"),
    counter.getAttribute("data-tree-counter"), getComputedStyle(counter, "::before").content,
    root.hasAttribute("textfox-tree-line")];
  arrow.click();
  await nextFrame();
  await nextFrame();
  return {
    showTree, lines, contrast, matchingGuideColors, collapsed,
    parentsUnloaded: !root.linkedPanel && !child.linkedPanel,
    worksInRail: !tabs.hasAttribute("expanded") &&
      arrow.getAttribute("aria-expanded") === "true" && !child.hasAttribute("data-tree-hidden") &&
      root.hasAttribute("textfox-tree-line"),
  };
} finally {
  chromeStyle.setProperty("--tf-accent", originalAccent, originalPriority);
  for (const tab of [grandchild, child, sibling, root, plain]) gBrowser.removeTab(tab, { animate: false });
  if (wasExpanded) controller.handleToolbarButtonClick();
}
})();
""")
    assert state["showTree"] == ["block", "true", "2px", "2px", "4px", "none"], state
    assert state["lines"] == [
        ["2px 100%", "1px 50%"],
        ["2px 0px, 4px 100%", "1px 100%, 1px 50%"],
        ["2px 0px, 4px 0px", "1px 100%, 1px 50%"],
        ["2px 0px", "1px 50%"],
        ["0% 0%", "auto"],
    ], state
    assert state["collapsed"] == ["false", True, "3", "attr(data-tree-counter)", False], state
    assert state["contrast"] >= 60 and state["matchingGuideColors"], state
    assert state["worksInRail"] and state["parentsUnloaded"], state
    print("PASS collapsed sidebar draws continuous guides from each parent to its last visible child")


def check_tree_reorder_keeps_root(execute):
    execute("""
const [source, root, child, last, next] = Array.from({ length: 5 }, () =>
  gBrowser.addTrustedTab("about:blank", { skipAnimation: true })
);
gBrowser.TreeTabsService.attachTab(child, root);
gBrowser.TreeTabsService.attachTab(last, root);
const transfer = new DataTransfer();
const boxes = [source, root, child].map(tab => tab.getBoundingClientRect());
const eventAt = (type, index, yOffset, xOffset) => {
  const box = boxes[index];
  const x = Math.round(box.left + box.width * xOffset);
  const y = Math.round(box.top + box.height * yOffset);
  return new DragEvent(type, {
    bubbles: true, cancelable: true, dataTransfer: transfer, clientX: x, clientY: y,
    screenX: window.mozInnerScreenX + x, screenY: window.mozInnerScreenY + y,
  });
};
window.textfoxTestTree = { source, root, child, last, next, eventAt };
source.dispatchEvent(eventAt("dragstart", 0, 0.5, 0.3));
transfer.dropEffect = "move";
root.dispatchEvent(eventAt("dragover", 1, 0.5, 0.75));
child.dispatchEvent(eventAt("dragover", 2, 0.54, 0.75));
""")
    try:
        wait_for(
            lambda: execute("""
const { last } = window.textfoxTestTree;
const line = document.getElementById("textfox-tab-drop-position");
return !line.hidden &&
  Math.abs(line.getBoundingClientRect().top + 1.5 - last.getBoundingClientRect().bottom) < 1;
"""),
            bool, "root insertion marker after the entire branch",
        )
        execute("""
const { child, eventAt } = window.textfoxTestTree;
child.dispatchEvent(eventAt("drop", 2, 0.54, 0.75));
""")
        wait_for(
            lambda: execute("""
const { source, root, child, last, next } = window.textfoxTestTree;
const service = gBrowser.TreeTabsService;
return !service.getParent(source) && service.getParent(child) === root
  && service.getParent(last) === root && source._tPos === last._tPos + 1
  && next._tPos === source._tPos + 1;
"""),
            bool, "regular drag stays at root and lands at the indicated gap",
        )
    finally:
        execute("""
gBrowser.tabContainer.tabDragAndDrop.finishAnimateTabMove();
const { source, root, child, last, next } = window.textfoxTestTree;
for (const tab of [source, child, last, root, next]) gBrowser.removeTab(tab, { animate: false });
delete window.textfoxTestTree;
""")
    print("PASS unmodified tree drag reorders after a foreign subtree without nesting")


def check_pinned_row_drop(execute):
    execute("""
const controller = window.SidebarController;
if (!controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
const pins = [];
for (let i = 0; i < 6; i++) {
  const tab = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
  gBrowser.pinTab(tab);
  pins.push(tab);
}
window.textfoxTestPins = { pins };
""")
    try:
        wait_for(
            lambda: execute("""
const { pins } = window.textfoxTestPins;
const rows = pins.map(tab => tab.getBoundingClientRect().top);
return gBrowser.tabContainer.isContainerVerticalPinnedGrid(pins[0])
  && rows[0] === rows[2] && rows[2] < rows[3] && rows[3] === rows[5];
"""),
            bool, "two pinned rows ready for drag",
        )
        execute("""
const drag = window.textfoxTestPins;
const [first] = drag.pins;
const transfer = new DataTransfer();
drag.boxes = drag.pins.map(tab => tab.getBoundingClientRect());
drag.eventAt = (type, index) => {
  const box = drag.boxes[index];
  const x = Math.round(box.left + box.width / 2);
  const y = Math.round(box.top + box.height / 2);
  return new DragEvent(type, {
    bubbles: true, cancelable: true, dataTransfer: transfer, clientX: x, clientY: y,
    screenX: window.mozInnerScreenX + x, screenY: window.mozInnerScreenY + y,
  });
};
first.dispatchEvent(drag.eventAt("dragstart", 0));
transfer.dropEffect = "move";
drag.pins[1].dispatchEvent(drag.eventAt("dragover", 1));
""")
        for index in (2, 3):
            execute("""
const { pins, eventAt } = window.textfoxTestPins;
const index = arguments[0];
pins[index].dispatchEvent(eventAt("dragover", index));
""", index)
            wait_for(
                lambda: execute("""
const indicator = document.getElementById("textfox-tab-drop-position");
if (indicator.hidden) return null;
const index = arguments[0];
const { boxes, pins } = window.textfoxTestPins;
const line = indicator.getBoundingClientRect();
const aligned = index === 3
  ? line.height === 3 && Math.abs(line.top + 1.5 - boxes[index].top) < 1
  : line.width === 3 && Math.abs(line.left + 1.5 - boxes[index].left) < 1
    && Math.abs(line.top - boxes[index].top) <= 2;
return { aligned, nativeIndex: pins[0]._dragData?.animDropElementIndex,
         line: [line.left, line.top, line.width, line.height],
         expected: [boxes[index].left, boxes[index].top] };
""", index),
                lambda marker: marker["aligned"], f"pinned grid marker at slot {index}",
            )
        execute("""
const { pins, eventAt } = window.textfoxTestPins;
pins[3].dispatchEvent(eventAt("drop", 3));
""")
        wait_for(
            lambda: execute("""
return window.textfoxTestPins.pins[0]._tPos === 3
  && document.getElementById("textfox-tab-drop-position").hidden;
"""),
            bool, "pinned tab moved to the start of the next row",
        )
    finally:
        execute("""
gBrowser.tabContainer.tabDragAndDrop.finishAnimateTabMove();
for (const tab of window.textfoxTestPins.pins) gBrowser.removeTab(tab, { animate: false });
delete window.textfoxTestPins;
const controller = window.SidebarController;
if (controller.sidebarMain.expanded) controller.handleToolbarButtonClick();
""")
    print("PASS pinned drop marker follows the destination slot across rows")


def main():
    browser = browser_argument(__doc__)
    tab_height = "return gBrowser.selectedTab.getBoundingClientRect().height;"
    with gecko_profile(browser, theme_dir=ROOT) as (_, _, execute):
        assert not execute("return Services.prefs.getBoolPref('sidebar.verticalTabs', false);")
        assert execute(tab_height) > 0, "Selected horizontal tab is invisible in a fresh profile"
        check_tab_states(execute, "horizontal")
        check_density(execute)
        execute("document.documentElement.style.setProperty('--tf-display-horizontal-tabs', 'none');")
        assert execute(tab_height) == 0, "Explicit horizontal tab override was ignored"
        print("PASS fresh profile shows horizontal tabs and respects explicit hiding")
        execute("document.documentElement.style.removeProperty('--tf-display-horizontal-tabs');")
        check_waterfox_appearance(execute, "horizontal")
        check_native_density(execute)
        check_sine_preferences(execute)
        check_sine_area_titles(execute)
        check_compact_frame_titles(execute)
        check_tab_drop_position(execute, "horizontal")
        check_tab_move_menu(execute, "horizontal")
    with gecko_profile(browser, preferences=PREFERENCES, theme_dir=ROOT) as (_, _, execute):
        info = execute("return [Services.appinfo.name, Services.appinfo.version];")
        if info[0].lower() != "waterfox":
            raise RuntimeError(f"This test requires Waterfox, received {info[0]}.")
        print(f"Waterfox {info[1]}")
        assert execute(tab_height) > 0, "Selected vertical tab is invisible"
        assert execute("return document.getElementById('TabsToolbar').getBoundingClientRect().height;") == 0
        check_tab_states(execute, "vertical")
        check_density(execute, vertical=True)
        check_sine_urlbar_and_status(execute)
        check_colors(execute)
        check_sidebar(execute)
        check_collapsed_tab_frames(execute)
        check_collapsed_tree_cues(execute)
        check_sine_area_titles(execute, vertical=True)
        check_sine_tree_guides(execute)
        check_sine_area_colors(execute)
        check_tab_hover_preview(execute)
        check_status_and_motion(execute)
        execute("window.fullScreen = false;")
        check_waterfox_appearance(execute, "vertical")
        check_frame_spacing(execute)
        check_tab_drop_position(execute, "vertical")
        check_shift_drop_requires_parent(execute)
        check_tree_reorder_keeps_root(execute)
        check_compact_frame_titles(execute, vertical=True)
        check_expanded_pinned_grid(execute)
        check_pinned_favicon_cache(execute)
        check_pinned_row_drop(execute)
        check_tab_move_menu(execute, "vertical")


if __name__ == "__main__":
    main()
