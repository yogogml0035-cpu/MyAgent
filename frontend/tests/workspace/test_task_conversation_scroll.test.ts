import assert from "node:assert/strict";
import test from "node:test";

import {
  LOG_LIST_AUTO_SCROLL_THRESHOLD,
  collapseOpenLogDetails,
  countOpenLogDetails,
  isLogListNearBottom,
  scrollLogListToBottomIfPinned,
} from "../../components/chat/TaskConversation";

function scrollElement(options: {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
}) {
  const calls: ScrollToOptions[] = [];
  return {
    calls,
    element: {
      ...options,
      scrollTo(options: ScrollToOptions) {
        calls.push(options);
      },
    },
  };
}

test("isLogListNearBottom treats log lists inside the threshold as pinned", () => {
  const { element } = scrollElement({
    clientHeight: 280,
    scrollHeight: 1000,
    scrollTop: 1000 - 280 - LOG_LIST_AUTO_SCROLL_THRESHOLD,
  });

  assert.equal(isLogListNearBottom(element), true);
});

test("scrollLogListToBottomIfPinned keeps a growing pinned log list at the bottom", () => {
  const { element, calls } = scrollElement({
    clientHeight: 280,
    scrollHeight: 1400,
    scrollTop: 700,
  });

  assert.equal(scrollLogListToBottomIfPinned(element, true), true);
  assert.deepEqual(calls, [{ top: 1400, behavior: "auto" }]);
});

test("scrollLogListToBottomIfPinned does not fight intentional upward scrolling", () => {
  const { element, calls } = scrollElement({
    clientHeight: 280,
    scrollHeight: 1400,
    scrollTop: 200,
  });

  assert.equal(scrollLogListToBottomIfPinned(element, false), false);
  assert.deepEqual(calls, []);
});

test("collapseOpenLogDetails closes every expanded progress log row", () => {
  const firstDetail = { open: true };
  const secondDetail = { open: true };
  const containers = [
    {
      querySelectorAll(selector: string) {
        assert.equal(selector, "details[open]");
        return [firstDetail, secondDetail];
      },
    },
    {
      querySelectorAll(selector: string) {
        assert.equal(selector, "details[open]");
        return [];
      },
    },
  ] as unknown as HTMLElement[];

  assert.equal(countOpenLogDetails(containers), 2);
  assert.equal(collapseOpenLogDetails(containers), 2);
  assert.deepEqual([firstDetail.open, secondDetail.open], [false, false]);
});
