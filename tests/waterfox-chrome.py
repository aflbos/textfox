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
    wait_for(lambda: execute(expanded), bool, "expanded vertical tabs")
    assert execute("""
const { TreeTabsService } = ChromeUtils.importESModule("resource:///modules/TreeTabsService.sys.mjs");
const parent = gBrowser.selectedTab;
const child = gBrowser.addTrustedTab("about:blank", { skipAnimation: true });
child.id = "textfox-guide-test-child";
return TreeTabsService.attachTab(child, parent);
""")
    read = """
const child = document.getElementById("textfox-guide-test-child");
if (child.dataset.treeLevel !== "1") return null;
const css = getComputedStyle(child);
return [css.borderInlineStartColor, css.borderInlineStartWidth, css.marginInlineStart];
"""
    native = wait_for(lambda: execute(read), lambda style: style[2] != "0px", "Waterfox tree indentation")
    execute('Services.prefs.setStringPref("textfox.sine.treeGuides", "accent");')
    accent = wait_for(lambda: execute(read), lambda style: style[1] == "1px" and style[0] != native[0], "Textfox tree guide")
    assert accent[2] == native[2], (accent, native)
    execute('Services.prefs.setStringPref("textfox.sine.treeGuides", "hidden");')
    hidden = wait_for(lambda: execute(read), lambda style: style[0] == "rgba(0, 0, 0, 0)", "hidden tree guide")
    assert hidden[2] == native[2], (hidden, native)
    execute(toggle)
    wait_for(lambda: execute(expanded), lambda value: not value, "collapsed vertical tabs")
    collapsed = execute(read)
    assert collapsed[0] != hidden[0], collapsed
    execute("""
Services.prefs.clearUserPref("textfox.sine.treeGuides");
gBrowser.removeTab(document.getElementById("textfox-guide-test-child"), { animate: false });
""")
    print("PASS native, accented and hidden hierarchy guides on a real child tab")


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
const eventAt = (type, tab, offset) => {
  const r = tab.getBoundingClientRect();
  const x = Math.round(r.left + r.width * offset);
  const y = Math.round(r.top + r.height * offset);
  return new DragEvent(type, {
    bubbles: true, cancelable: true, dataTransfer: transfer, clientX: x, clientY: y,
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
        execute("""
const drag = window.textfoxTestDrag;
const event = drag.eventAt("dragover", drag.third, 0.5);
drag.third.dispatchEvent(event);
drag.childTarget = gBrowser.tabContainer.querySelector('[data-tree-drop-target="child"]');
drag.childDrop = new DragEvent("drop", {
  bubbles: true, cancelable: true, dataTransfer: event.dataTransfer,
  clientX: event.clientX, clientY: event.clientY, screenX: event.screenX, screenY: event.screenY,
});
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
        check_sine_area_titles(execute, vertical=True)
        check_sine_tree_guides(execute)
        check_sine_area_colors(execute)
        check_tab_hover_preview(execute)
        check_status_and_motion(execute)
        execute("window.fullScreen = false;")
        check_waterfox_appearance(execute, "vertical")
        check_frame_spacing(execute)
        check_tab_drop_position(execute, "vertical")
        check_compact_frame_titles(execute, vertical=True)


if __name__ == "__main__":
    main()
