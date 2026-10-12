import {afterEach,expect,test} from "bun:test";
import {htmlFetch,extractDivContent,parseJobDetail} from "../src/helpers";
const original=globalThis.fetch;
afterEach(()=>{globalThis.fetch=original;});
test("429 carries publisher Retry-After and never retries",async()=>{
  let calls=0;
  globalThis.fetch=(async()=>{calls++;return new Response("",{status:429,headers:{'Retry-After':'120'}});}) as typeof fetch;
  try {await htmlFetch('https://www.linkedin.com/test');throw new Error('Expected refusal');}
  catch(error){expect((error as any).http_status).toBe(429);expect((error as any).retry_after).toBe('120');}
  expect(calls).toBe(1);
});
test("JobSpy description-container convention supports single quotes and nested mixed-case DIV",()=>{
  const html="<DIV class='show-more-less-html__markup'><div>Lead people</div><DIV>Coach engineers</DIV></DIV><div>Unrelated footer</div>";
  expect(extractDivContent(html,'show-more-less-html__markup')).toBe('<div>Lead people</div><DIV>Coach engineers</DIV>');
  const job=parseJobDetail(html,'123456');
  expect(job.description).toContain('Lead people');expect(job.description).toContain('Coach engineers');expect(job.description).not.toContain('Unrelated footer');
});
test("missing or lookalike container stays missing, never an invented description",()=>{
  expect(extractDivContent('<div class="show-more-less-html__markup-other">Wrong content</div>','show-more-less-html__markup')).toBeNull();
  expect(parseJobDetail('<html></html>','123456').description).toBeNull();
});
