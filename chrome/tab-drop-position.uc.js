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
    tabs.removeAttribute("textfox-drop-between");
  }

  const dragAndDrop = tabs.tabDragAndDrop;
  const updateTabStyles = dragAndDrop?._updateTabStylesOnDrag;
  const treeDnD = window.TreeTabsDnD;
  const nativeAttachTarget = treeDnD?.getAttachTarget;
  const nativePlacementBetween = treeDnD?._placementBetween;
  const centeredDrags = new WeakSet();
  const rootPlacements = new WeakSet();

  function isLocalMove(container, event, dragged) {
    return container === tabs && dragged?.container === tabs && !dragged.multiselected &&
      !dragged._dragData?.fromTabList && dragAndDrop?.getDropEffectForTabDrag(event) === "move";
  }

  function getAttachTarget(container, event, dragged, ...args) {
    const target = nativeAttachTarget.call(this, container, event, dragged, ...args);
    if (!target || !isLocalMove(container, event, dragged)) return target;
    if (!event.shiftKey) return null;

    const child = this._getLogicalTab(dragged);
    const service = window.gBrowser.TreeTabsService;
    const state = service._getStateForTab?.(child)?.state;
    return child.group === target.group &&
      !(state && service._wouldExceedMaxDepth?.(state, target, child)) ? target : null;
  }

  function placementBetween(service, previous, next, dragged, event, movingSet) {
    const placement = nativePlacementBetween.call(this, service, previous, next, dragged, event, movingSet);
    if (!placement?.parent || !event || !isLocalMove(tabs, event, dragged) ||
        placement.parent === service.getParent(this._getLogicalTab(dragged))) {
      return placement;
    }

    // An insertion line inside another subtree must not change the parent.
    const root = service.getAncestors(previous).at(-1) ?? previous;
    const replacement = { parent: null, insertAfter: root };
    rootPlacements.add(replacement);
    return replacement;
  }

  if (typeof nativeAttachTarget === "function") {
    treeDnD.getAttachTarget = getAttachTarget;
  }
  if (typeof nativePlacementBetween === "function") {
    treeDnD._placementBetween = placementBetween;
  }

  function centerDraggedTab(dragged, dropEffect) {
    const result = updateTabStyles.call(this, dragged, dropEffect);
    const data = dragged._dragData;
    if (dropEffect === "move" && dragged.classList.contains("tabbrowser-tab") &&
        dragged.hasAttribute("dragtarget") && data && !centeredDrags.has(data)) {
      // Gecko positions the dragged tab absolutely before translating it.
      // Read its center after that layout change and keep detachment offsets.
      const rect = dragged.getBoundingClientRect();
      data.screenX = dragged.screenX + rect.width / 2;
      data.screenY = dragged.screenY + rect.height / 2;
      centeredDrags.add(data);
    }
    return result;
  }

  if (typeof updateTabStyles === "function") {
    dragAndDrop._updateTabStylesOnDrag = centerDraggedTab;
  }

  function maskBehindDraggedTab(dragged, vertical, edge, start, end) {
    const frame = dragged.querySelector(":scope > .tab-stack > .tab-background") ?? dragged;
    const bounds = frame.getBoundingClientRect();
    const nearEdge = vertical ? bounds.top : bounds.left;
    const farEdge = vertical ? bounds.bottom : bounds.right;
    const coverStart = Math.max(start, vertical ? bounds.left : bounds.top);
    const coverEnd = Math.min(end, vertical ? bounds.right : bounds.bottom);
    if (edge + 1.5 <= nearEdge || edge - 1.5 >= farEdge || coverEnd <= coverStart) {
      return "none";
    }

    // The native tab may be in a different stacking context. Cut the line
    // out behind its painted frame so it remains visible in the gutters.
    const from = `${coverStart - start}px`;
    const to = `${coverEnd - start}px`;
    const direction = vertical ? "to right" : "to bottom";
    return `linear-gradient(${direction}, currentColor ${from}, transparent ${from} ${to}, currentColor ${to})`;
  }

  function getPinnedSlot(data, target, item, rtl) {
    const index = data.animDropElementIndex;
    const columns = dragAndDrop?._maxTabsPerRow;
    const reference = target.currentIndex ?? target.elementIndex;
    if (!Number.isInteger(index) || !Number.isInteger(reference) || !columns) return null;

    // The native index counts the moved tabs. The new slot does not.
    const slot = index - data.movingTabs.filter(tab => tab.elementIndex < index).length;
    const column = slot % columns;
    const columnDelta = column - reference % columns;
    const rowDelta = Math.floor(slot / columns) - Math.floor(reference / columns);
    const transform = new DOMMatrixReadOnly(getComputedStyle(target).transform);
    const left = item.left - transform.m41 + columnDelta * item.width * (rtl ? -1 : 1);
    const top = item.top - transform.m42 + rowDelta * item.height;
    return {
      rect: new DOMRect(left, top, item.width, item.height),
      rowBreak: slot > 0 && column === 0,
    };
  }

  function showPosition(dragged, afterBranch) {
    const data = dragged._dragData;
    const target = afterBranch ?? data?.dropElement;
    if (!target?.isConnected || (!afterBranch && typeof data.dropBefore !== "boolean")) {
      return false;
    }

    const item = target.getBoundingClientRect();
    if (!item.width || !item.height) {
      return false;
    }

    const grid = tabs.isContainerVerticalPinnedGrid?.(dragged);
    const rtl = getComputedStyle(tabs).direction === "rtl";
    const slot = grid ? getPinnedSlot(data, target, item, rtl) : null;
    const vertical = tabs.verticalMode && (!grid || slot?.rowBreak);
    const viewport = (dragged.pinned
      ? tabs.pinnedTabsContainer?.getBoundingClientRect()
      : tabs.arrowScrollbox?.scrollClientRect) ?? tabs.getBoundingClientRect();
    const destination = slot?.rect ?? item;
    const before = !afterBranch && (Boolean(slot) || data.dropBefore);
    const drawBefore = vertical ? before : before !== rtl;
    const targetEdge = vertical
      ? (drawBefore ? destination.top : destination.bottom)
      : (drawBefore ? destination.left : destination.right);
    const span = slot?.rowBreak ? viewport : destination;
    const start = vertical ? Math.max(span.left, viewport.left) : Math.max(span.top, viewport.top);
    const end = vertical ? Math.min(span.right, viewport.right) : Math.min(span.bottom, viewport.bottom);
    const axisStart = vertical ? viewport.top : viewport.left;
    const axisEnd = vertical ? viewport.bottom : viewport.right;
    if (end <= start) {
      return false;
    }

    const edge = Math.max(axisStart, Math.min(targetEdge, axisEnd));
    indicator.dataset.axis = vertical ? "vertical" : "horizontal";
    indicator.style.left = `${vertical ? start : edge}px`;
    indicator.style.top = `${vertical ? edge : start}px`;
    indicator.style.setProperty("--textfox-drop-span", `${end - start}px`);
    indicator.style.maskImage = maskBehindDraggedTab(dragged, vertical, edge, start, end);
    return true;
  }

  function followPosition(dragged, afterBranch) {
    if (!tabs.hasAttribute("movingtab")) {
      hide();
      return;
    }
    const visible = showPosition(dragged, afterBranch);
    indicator.hidden = !visible;
    tabs.toggleAttribute("textfox-drop-between", visible);
    update = window.requestAnimationFrame(() => followPosition(dragged, afterBranch));
  }

  tabs.addEventListener("dragover", event => {
    // Use the index computed by the browser after its own dragover handler,
    // and keep the native indicator for copies, links and cross-window drops.
    hide();
    const transfer = event.dataTransfer;
    const dragged = transfer?.mozItemCount ? transfer.mozGetDataAt(tabType, 0) : null;
    if (!event.defaultPrevented || dragged?.ownerDocument !== document ||
        !tabs.tabDragAndDrop?._tabDropIndicator?.hidden || dragged._dragData?.fromTabList) {
      return;
    }
    let afterBranch;
    if (treeDnD?._isEnabled?.(tabs) && !dragged.pinned && isLocalMove(tabs, event, dragged)) {
      // Waterfox already highlights the parent for an explicit attachment.
      if (treeDnD.getAttachTarget(tabs, event, dragged)) return;
      const placement = treeDnD._previewDropPlacement?.(event, dragged);
      if (rootPlacements.has(placement)) {
        const service = window.gBrowser.TreeTabsService;
        const moving = treeDnD._getMovingSet(treeDnD._getLogicalTab(dragged));
        afterBranch = service.getDescendants(placement.insertAfter).findLast(
          tab => treeDnD._isPlacementCandidate(tab, moving)
        ) ?? placement.insertAfter;
      }
    }
    update = window.requestAnimationFrame(() => followPosition(dragged, afterBranch));
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
    if (dragAndDrop?._updateTabStylesOnDrag === centerDraggedTab) {
      dragAndDrop._updateTabStylesOnDrag = updateTabStyles;
    }
    if (treeDnD?.getAttachTarget === getAttachTarget) {
      treeDnD.getAttachTarget = nativeAttachTarget;
    }
    if (treeDnD?._placementBetween === placementBetween) {
      treeDnD._placementBetween = nativePlacementBetween;
    }
  });
})();
