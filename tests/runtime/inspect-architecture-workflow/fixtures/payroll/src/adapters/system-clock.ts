import type { Clock } from "../domain/clock";

export class SystemClock implements Clock {
  now(): Date {
    return new Date();
  }
}
