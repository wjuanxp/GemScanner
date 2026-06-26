#pragma once
typedef enum { ST_DISCONNECTED, ST_IDLE, ST_MOVING, ST_SETTLING } disp_state_t;
void status_display_init(void);
void status_display_set(disp_state_t state, double angle_deg, long steps);
