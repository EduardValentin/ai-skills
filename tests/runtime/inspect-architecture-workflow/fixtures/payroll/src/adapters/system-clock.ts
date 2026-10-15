import type { Clock } from "../domain";

export class SystemClock implements Clock {
  now(): Date {
    return new Date();
  }
}
