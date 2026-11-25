(() => {
  "use strict";

  const tabs = window.gBrowser?.tabContainer;
  if (!tabs || document.getElementById("textfox-tab-drop-position")) {
    return;
  }

  const indicator = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
  indicator.id = "textfox-tab-drop-position";
  indicator.setAttribute("aria-hidden", "true");
  indicator.hidden = true;
  document.body.append(indicator);

  const controller = new AbortController();
  const { signal } = controller;
  const tabType = "application/x-moz-tabbrowser-tab";
  let update = 0;

  function hide() {
    window.cancelAnimationFrame(update);
    indicator.hidden = true;
  }

  function showPosition(dragged) {
    const data = dragged._dragData;
    const target = data?.dropElement;
    if (!tabs.hasAttribute("movingtab") || !target?.isConnected || typeof data.dropBefore !== "boolean") {
      return;
    }

    const item = target.getBoundingClientRect();
    if (!item.width || !item.height) {
      return;
    }

    const vertical = tabs.verticalMode && !tabs.isContainerVerticalPinnedGrid?.(dragged);
    const rtl = getComputedStyle(tabs).direction === "rtl";
    const viewport = (dragged.pinned
      ? tabs.pinnedTabsContainer?.getBoundingClientRect()
      : tabs.arrowScrollbox?.scrollClientRect) ?? tabs.getBoundingClientRect();
    const drawBefore = vertical ? data.dropBefore : data.dropBefore !== rtl;
    const targetEdge = vertical
      ? (drawBefore ? item.top : item.bottom)
      : (drawBefore ? item.left : item.right);
    const start = vertical ? Math.max(item.left, viewport.left) : Math.max(item.top, viewport.top);
    const end = vertical ? Math.min(item.right, viewport.right) : Math.min(item.bottom, viewport.bottom);
    const axisStart = vertical ? viewport.top : viewport.left;
    const axisEnd = vertical ? viewport.bottom : viewport.right;
    if (end <= start) {
      return;
    }

    const edge = Math.max(axisStart, Math.min(targetEdge, axisEnd));
    indicator.dataset.axis = vertical ? "vertical" : "horizontal";
    indicator.style.left = `${vertical ? start : edge}px`;
    indicator.style.top = `${vertical ? edge : start}px`;
    indicator.style.setProperty("--textfox-drop-span", `${end - start}px`);
    indicator.hidden = false;
  }

  tabs.addEventListener("dragover", event => {
    // Use the index computed by the browser after its own dragover handler,
    // and keep the native indicator for copies, links and cross-window drops.
    window.cancelAnimationFrame(update);
    const transfer = event.dataTransfer;
    const dragged = transfer?.mozItemCount ? transfer.mozGetDataAt(tabType, 0) : null;
    if (!event.defaultPrevented || dragged?.ownerDocument !== document ||
        !tabs.tabDragAndDrop?._tabDropIndicator?.hidden || dragged._dragData?.fromTabList) {
      hide();
      return;
    }
    // Waterfox already highlights the parent for a drop that creates a child.
    if (window.TreeTabsDnD?.getAttachTarget?.(tabs, event, dragged)) {
      hide();
      return;
    }
    update = window.requestAnimationFrame(() => {
      indicator.hidden = true;
      showPosition(dragged);
    });
  }, { signal });

  tabs.addEventListener("dragleave", event => {
    if (!tabs.contains(event.relatedTarget)) {
      hide();
    }
  }, { signal });
  window.addEventListener("dragend", hide, { capture: true, signal });
  window.addEventListener("drop", hide, { capture: true, signal });
  window.addEventListener("blur", hide, { signal });
  window.addUnloadListener?.(() => {
    hide();
    controller.abort();
    indicator.remove();
  });
})();
