export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type Database = {
  public: {
    Tables: {
      audit_logs: {
        Row: {
          action: string;
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at: string;
          id: string;
          metadata: Json;
          new_version: number | null;
          old_version: number | null;
          owner_id: string;
          request_id: string;
          target_id: string | null;
          target_type: string;
        };
        Insert: {
          action: string;
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          id?: string;
          metadata?: Json;
          new_version?: number | null;
          old_version?: number | null;
          owner_id: string;
          request_id: string;
          target_id?: string | null;
          target_type: string;
        };
        Update: {
          action?: string;
          actor_id?: string;
          actor_type?: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          id?: string;
          metadata?: Json;
          new_version?: number | null;
          old_version?: number | null;
          owner_id?: string;
          request_id?: string;
          target_id?: string | null;
          target_type?: string;
        };
        Relationships: [
          {
            foreignKeyName: "audit_logs_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      broker_orders: {
        Row: {
          broker_order_reference: string | null;
          broker_result_code: string | null;
          broker_result_message: string | null;
          created_at: string;
          direction: Database["public"]["Enums"]["trade_direction"];
          id: string;
          owner_id: string;
          requested_price: number | null;
          requested_volume: number;
          status: Database["public"]["Enums"]["broker_order_status"];
          stop_loss_price: number;
          system_command_id: string;
          take_profit_price: number;
          trade_proposal_id: string;
          trading_account_id: string;
          updated_at: string;
        };
        Insert: {
          broker_order_reference?: string | null;
          broker_result_code?: string | null;
          broker_result_message?: string | null;
          created_at?: string;
          direction: Database["public"]["Enums"]["trade_direction"];
          id?: string;
          owner_id: string;
          requested_price?: number | null;
          requested_volume: number;
          status: Database["public"]["Enums"]["broker_order_status"];
          stop_loss_price: number;
          system_command_id: string;
          take_profit_price: number;
          trade_proposal_id: string;
          trading_account_id: string;
          updated_at?: string;
        };
        Update: {
          broker_order_reference?: string | null;
          broker_result_code?: string | null;
          broker_result_message?: string | null;
          created_at?: string;
          direction?: Database["public"]["Enums"]["trade_direction"];
          id?: string;
          owner_id?: string;
          requested_price?: number | null;
          requested_volume?: number;
          status?: Database["public"]["Enums"]["broker_order_status"];
          stop_loss_price?: number;
          system_command_id?: string;
          take_profit_price?: number;
          trade_proposal_id?: string;
          trading_account_id?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "broker_orders_system_command_id_owner_id_fkey";
            columns: ["system_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_command_read_models";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "broker_orders_system_command_id_owner_id_fkey";
            columns: ["system_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_commands";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "broker_orders_trade_proposal_id_owner_id_trading_account_i_fkey";
            columns: ["trade_proposal_id", "owner_id", "trading_account_id"];
            isOneToOne: false;
            referencedRelation: "trade_proposals";
            referencedColumns: ["id", "owner_id", "trading_account_id"];
          },
          {
            foreignKeyName: "broker_orders_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      broker_symbols: {
        Row: {
          account_currency: string;
          base_currency: string | null;
          broker_symbol: string;
          calculation_mode: string;
          canonical_symbol: string;
          confirmation_status: string;
          confirmation_version: number | null;
          confirmed_at: string | null;
          confirmed_by: string | null;
          confirmed_specification_fingerprint: string | null;
          contract_size: number;
          created_at: string;
          digits: number;
          fetched_at: string;
          id: string;
          maximum_volume: number;
          minimum_volume: number;
          owner_id: string;
          point_size: number;
          profit_currency: string | null;
          specification_version: string;
          stop_level: number;
          tick_size: number;
          tick_value: number | null;
          trading_account_id: string;
          volume_step: number;
        };
        Insert: {
          account_currency: string;
          base_currency?: string | null;
          broker_symbol: string;
          calculation_mode: string;
          canonical_symbol?: string;
          confirmation_status?: string;
          confirmation_version?: number | null;
          confirmed_at?: string | null;
          confirmed_by?: string | null;
          confirmed_specification_fingerprint?: string | null;
          contract_size: number;
          created_at?: string;
          digits: number;
          fetched_at: string;
          id?: string;
          maximum_volume: number;
          minimum_volume: number;
          owner_id: string;
          point_size: number;
          profit_currency?: string | null;
          specification_version: string;
          stop_level: number;
          tick_size: number;
          tick_value?: number | null;
          trading_account_id: string;
          volume_step: number;
        };
        Update: {
          account_currency?: string;
          base_currency?: string | null;
          broker_symbol?: string;
          calculation_mode?: string;
          canonical_symbol?: string;
          confirmation_status?: string;
          confirmation_version?: number | null;
          confirmed_at?: string | null;
          confirmed_by?: string | null;
          confirmed_specification_fingerprint?: string | null;
          contract_size?: number;
          created_at?: string;
          digits?: number;
          fetched_at?: string;
          id?: string;
          maximum_volume?: number;
          minimum_volume?: number;
          owner_id?: string;
          point_size?: number;
          profit_currency?: string | null;
          specification_version?: string;
          stop_level?: number;
          tick_size?: number;
          tick_value?: number | null;
          trading_account_id?: string;
          volume_step?: number;
        };
        Relationships: [
          {
            foreignKeyName: "broker_symbols_confirmed_by_fkey";
            columns: ["confirmed_by"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "broker_symbols_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      feature_snapshots: {
        Row: {
          captured_at: string;
          created_at: string;
          feature_schema_version: string;
          feature_values: Json;
          id: string;
          market_snapshot_id: string;
          owner_id: string;
          trading_account_id: string;
        };
        Insert: {
          captured_at: string;
          created_at?: string;
          feature_schema_version: string;
          feature_values: Json;
          id?: string;
          market_snapshot_id: string;
          owner_id: string;
          trading_account_id: string;
        };
        Update: {
          captured_at?: string;
          created_at?: string;
          feature_schema_version?: string;
          feature_values?: Json;
          id?: string;
          market_snapshot_id?: string;
          owner_id?: string;
          trading_account_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "feature_snapshots_market_snapshot_id_owner_id_trading_acco_fkey";
            columns: ["market_snapshot_id", "owner_id", "trading_account_id"];
            isOneToOne: false;
            referencedRelation: "market_snapshots";
            referencedColumns: ["id", "owner_id", "trading_account_id"];
          },
          {
            foreignKeyName: "feature_snapshots_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      market_snapshots: {
        Row: {
          age_ms: number;
          ask: number;
          atr: number;
          bid: number;
          canonical_symbol: string;
          captured_at: string;
          created_at: string;
          freshness: Database["public"]["Enums"]["market_freshness"];
          id: string;
          owner_id: string;
          regime: Database["public"]["Enums"]["market_regime"];
          session: Database["public"]["Enums"]["market_session"];
          spread_points: number;
          trading_account_id: string;
          transport: Database["public"]["Enums"]["market_transport"];
        };
        Insert: {
          age_ms: number;
          ask: number;
          atr: number;
          bid: number;
          canonical_symbol?: string;
          captured_at: string;
          created_at?: string;
          freshness: Database["public"]["Enums"]["market_freshness"];
          id?: string;
          owner_id: string;
          regime: Database["public"]["Enums"]["market_regime"];
          session: Database["public"]["Enums"]["market_session"];
          spread_points: number;
          trading_account_id: string;
          transport: Database["public"]["Enums"]["market_transport"];
        };
        Update: {
          age_ms?: number;
          ask?: number;
          atr?: number;
          bid?: number;
          canonical_symbol?: string;
          captured_at?: string;
          created_at?: string;
          freshness?: Database["public"]["Enums"]["market_freshness"];
          id?: string;
          owner_id?: string;
          regime?: Database["public"]["Enums"]["market_regime"];
          session?: Database["public"]["Enums"]["market_session"];
          spread_points?: number;
          trading_account_id?: string;
          transport?: Database["public"]["Enums"]["market_transport"];
        };
        Relationships: [
          {
            foreignKeyName: "market_snapshots_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      mt5_account_observations: {
        Row: {
          account_fingerprint: string;
          adapter_version: string;
          created_at: string;
          currency: string | null;
          id: string;
          leverage: number | null;
          masked_login: string;
          masked_server: string;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          server_fingerprint: string;
          source: string;
          trace_id: string;
          trade_mode: string;
          verification_state: string;
          worker_id: string;
        };
        Insert: {
          account_fingerprint: string;
          adapter_version: string;
          created_at?: string;
          currency?: string | null;
          id?: string;
          leverage?: number | null;
          masked_login: string;
          masked_server: string;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          server_fingerprint: string;
          source: string;
          trace_id: string;
          trade_mode: string;
          verification_state: string;
          worker_id: string;
        };
        Update: {
          account_fingerprint?: string;
          adapter_version?: string;
          created_at?: string;
          currency?: string | null;
          id?: string;
          leverage?: number | null;
          masked_login?: string;
          masked_server?: string;
          observed_at?: string;
          owner_id?: string;
          schema_version?: string;
          server_fingerprint?: string;
          source?: string;
          trace_id?: string;
          trade_mode?: string;
          verification_state?: string;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_account_observations_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      mt5_history_query_evidence: {
        Row: {
          created_at: string;
          earliest_returned_at: string | null;
          history_kind: string;
          id: string;
          latest_returned_at: string | null;
          owner_id: string;
          query_completed_at: string | null;
          reason_code: string;
          reconciliation_id: string;
          requested_end_at: string;
          requested_start_at: string;
          result_state: string;
          returned_count: number;
        };
        Insert: {
          created_at?: string;
          earliest_returned_at?: string | null;
          history_kind: string;
          id?: string;
          latest_returned_at?: string | null;
          owner_id: string;
          query_completed_at?: string | null;
          reason_code: string;
          reconciliation_id: string;
          requested_end_at: string;
          requested_start_at: string;
          result_state: string;
          returned_count: number;
        };
        Update: {
          created_at?: string;
          earliest_returned_at?: string | null;
          history_kind?: string;
          id?: string;
          latest_returned_at?: string | null;
          owner_id?: string;
          query_completed_at?: string | null;
          reason_code?: string;
          reconciliation_id?: string;
          requested_end_at?: string;
          requested_start_at?: string;
          result_state?: string;
          returned_count?: number;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_history_query_evidence_reconciliation_id_owner_id_fkey";
            columns: ["reconciliation_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "mt5_reconciliation_runs";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      mt5_latest_tick_observations: {
        Row: {
          account_fingerprint: string;
          adapter_version: string;
          age_seconds: number;
          ask: number;
          bid: number;
          broker_symbol: string;
          created_at: string;
          freshness: string;
          id: string;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          source: string;
          spread_points: number;
          spread_price: number;
          tick_at: string;
          trace_id: string;
          updated_at: string;
          version: number;
          worker_id: string;
        };
        Insert: {
          account_fingerprint: string;
          adapter_version: string;
          age_seconds: number;
          ask: number;
          bid: number;
          broker_symbol: string;
          created_at?: string;
          freshness: string;
          id?: string;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          source: string;
          spread_points: number;
          spread_price: number;
          tick_at: string;
          trace_id: string;
          updated_at?: string;
          version?: number;
          worker_id: string;
        };
        Update: {
          account_fingerprint?: string;
          adapter_version?: string;
          age_seconds?: number;
          ask?: number;
          bid?: number;
          broker_symbol?: string;
          created_at?: string;
          freshness?: string;
          id?: string;
          observed_at?: string;
          owner_id?: string;
          schema_version?: string;
          source?: string;
          spread_points?: number;
          spread_price?: number;
          tick_at?: string;
          trace_id?: string;
          updated_at?: string;
          version?: number;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_latest_tick_observations_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      mt5_reconciliation_mismatches: {
        Row: {
          category: string;
          created_at: string;
          id: string;
          owner_id: string;
          reason_code: string | null;
          reconciliation_id: string;
          resolution_state: string;
          resource_reference: string;
          resource_type: string;
          severity: string;
          worker_id: string;
        };
        Insert: {
          category: string;
          created_at?: string;
          id?: string;
          owner_id: string;
          reason_code?: string | null;
          reconciliation_id: string;
          resolution_state?: string;
          resource_reference: string;
          resource_type: string;
          severity: string;
          worker_id: string;
        };
        Update: {
          category?: string;
          created_at?: string;
          id?: string;
          owner_id?: string;
          reason_code?: string | null;
          reconciliation_id?: string;
          resolution_state?: string;
          resource_reference?: string;
          resource_type?: string;
          severity?: string;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_reconciliation_mismatches_reconciliation_id_owner_id_fkey";
            columns: ["reconciliation_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "mt5_reconciliation_runs";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      mt5_reconciliation_runs: {
        Row: {
          account_fingerprint: string | null;
          active_order_count: number;
          broker_symbol: string | null;
          completed_at: string | null;
          created_at: string;
          deal_history_count: number;
          id: string;
          mismatch_count: number;
          open_position_count: number;
          order_history_count: number;
          outcome: string | null;
          owner_id: string;
          reason_code: string;
          report_hash: string;
          server_fingerprint: string | null;
          started_at: string;
          status: string;
          symbol_specification_fingerprint: string | null;
          trace_id: string;
          updated_at: string;
          worker_id: string;
        };
        Insert: {
          account_fingerprint?: string | null;
          active_order_count?: number;
          broker_symbol?: string | null;
          completed_at?: string | null;
          created_at?: string;
          deal_history_count?: number;
          id: string;
          mismatch_count?: number;
          open_position_count?: number;
          order_history_count?: number;
          outcome?: string | null;
          owner_id: string;
          reason_code: string;
          report_hash: string;
          server_fingerprint?: string | null;
          started_at: string;
          status: string;
          symbol_specification_fingerprint?: string | null;
          trace_id: string;
          updated_at?: string;
          worker_id: string;
        };
        Update: {
          account_fingerprint?: string | null;
          active_order_count?: number;
          broker_symbol?: string | null;
          completed_at?: string | null;
          created_at?: string;
          deal_history_count?: number;
          id?: string;
          mismatch_count?: number;
          open_position_count?: number;
          order_history_count?: number;
          outcome?: string | null;
          owner_id?: string;
          reason_code?: string;
          report_hash?: string;
          server_fingerprint?: string | null;
          started_at?: string;
          status?: string;
          symbol_specification_fingerprint?: string | null;
          trace_id?: string;
          updated_at?: string;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_reconciliation_runs_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      mt5_symbol_observations: {
        Row: {
          account_fingerprint: string;
          adapter_version: string;
          broker_symbol: string;
          canonical_symbol: string;
          created_at: string;
          id: string;
          normalized_specification: Json;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          source: string;
          specification_fingerprint: string;
          trace_id: string;
          unusable_reason: string | null;
          usability_state: string;
          worker_id: string;
        };
        Insert: {
          account_fingerprint: string;
          adapter_version: string;
          broker_symbol: string;
          canonical_symbol: string;
          created_at?: string;
          id?: string;
          normalized_specification: Json;
          observed_at: string;
          owner_id: string;
          schema_version: string;
          source: string;
          specification_fingerprint: string;
          trace_id: string;
          unusable_reason?: string | null;
          usability_state: string;
          worker_id: string;
        };
        Update: {
          account_fingerprint?: string;
          adapter_version?: string;
          broker_symbol?: string;
          canonical_symbol?: string;
          created_at?: string;
          id?: string;
          normalized_specification?: Json;
          observed_at?: string;
          owner_id?: string;
          schema_version?: string;
          source?: string;
          specification_fingerprint?: string;
          trace_id?: string;
          unusable_reason?: string | null;
          usability_state?: string;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "mt5_symbol_observations_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      position_events: {
        Row: {
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at: string;
          detail: string;
          event_type: Database["public"]["Enums"]["position_event_type"];
          id: string;
          metadata: Json;
          occurred_at: string;
          owner_id: string;
          position_id: string;
          position_version: number;
        };
        Insert: {
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          detail: string;
          event_type: Database["public"]["Enums"]["position_event_type"];
          id?: string;
          metadata?: Json;
          occurred_at: string;
          owner_id: string;
          position_id: string;
          position_version: number;
        };
        Update: {
          actor_id?: string;
          actor_type?: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          detail?: string;
          event_type?: Database["public"]["Enums"]["position_event_type"];
          id?: string;
          metadata?: Json;
          occurred_at?: string;
          owner_id?: string;
          position_id?: string;
          position_version?: number;
        };
        Relationships: [
          {
            foreignKeyName: "position_events_position_id_owner_id_fkey";
            columns: ["position_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "positions";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      positions: {
        Row: {
          broker_order_id: string;
          broker_position_reference: string;
          closed_at: string | null;
          created_at: string;
          current_price: number;
          direction: Database["public"]["Enums"]["trade_direction"];
          entry_price: number;
          id: string;
          opened_at: string;
          owner_id: string;
          position_version: number;
          r_multiple: number;
          status: Database["public"]["Enums"]["position_status"];
          stop_loss_price: number;
          take_profit_price: number;
          trade_proposal_id: string;
          trading_account_id: string;
          unrealized_pnl: number;
          updated_at: string;
          volume: number;
        };
        Insert: {
          broker_order_id: string;
          broker_position_reference: string;
          closed_at?: string | null;
          created_at?: string;
          current_price: number;
          direction: Database["public"]["Enums"]["trade_direction"];
          entry_price: number;
          id?: string;
          opened_at: string;
          owner_id: string;
          position_version?: number;
          r_multiple?: number;
          status: Database["public"]["Enums"]["position_status"];
          stop_loss_price: number;
          take_profit_price: number;
          trade_proposal_id: string;
          trading_account_id: string;
          unrealized_pnl?: number;
          updated_at?: string;
          volume: number;
        };
        Update: {
          broker_order_id?: string;
          broker_position_reference?: string;
          closed_at?: string | null;
          created_at?: string;
          current_price?: number;
          direction?: Database["public"]["Enums"]["trade_direction"];
          entry_price?: number;
          id?: string;
          opened_at?: string;
          owner_id?: string;
          position_version?: number;
          r_multiple?: number;
          status?: Database["public"]["Enums"]["position_status"];
          stop_loss_price?: number;
          take_profit_price?: number;
          trade_proposal_id?: string;
          trading_account_id?: string;
          unrealized_pnl?: number;
          updated_at?: string;
          volume?: number;
        };
        Relationships: [
          {
            foreignKeyName: "positions_broker_order_id_owner_id_trading_account_id_trad_fkey";
            columns: [
              "broker_order_id",
              "owner_id",
              "trading_account_id",
              "trade_proposal_id",
            ];
            isOneToOne: false;
            referencedRelation: "broker_orders";
            referencedColumns: [
              "id",
              "owner_id",
              "trading_account_id",
              "trade_proposal_id",
            ];
          },
          {
            foreignKeyName: "positions_trade_proposal_id_owner_id_trading_account_id_fkey";
            columns: ["trade_proposal_id", "owner_id", "trading_account_id"];
            isOneToOne: false;
            referencedRelation: "trade_proposals";
            referencedColumns: ["id", "owner_id", "trading_account_id"];
          },
          {
            foreignKeyName: "positions_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      profiles: {
        Row: {
          created_at: string;
          display_name: string;
          id: string;
          locale: string;
          timezone: string;
          updated_at: string;
          version: number;
        };
        Insert: {
          created_at?: string;
          display_name?: string;
          id: string;
          locale?: string;
          timezone?: string;
          updated_at?: string;
          version?: number;
        };
        Update: {
          created_at?: string;
          display_name?: string;
          id?: string;
          locale?: string;
          timezone?: string;
          updated_at?: string;
          version?: number;
        };
        Relationships: [];
      };
      risk_checks: {
        Row: {
          actual: string;
          created_at: string;
          explanation: string | null;
          hard: boolean;
          id: string;
          key: string;
          label_en: string;
          label_th: string;
          limit_value: string | null;
          ordinal: number;
          owner_id: string;
          proposal_version: number;
          state: Database["public"]["Enums"]["risk_check_state"];
          trade_proposal_id: string;
        };
        Insert: {
          actual: string;
          created_at?: string;
          explanation?: string | null;
          hard: boolean;
          id?: string;
          key: string;
          label_en: string;
          label_th: string;
          limit_value?: string | null;
          ordinal: number;
          owner_id: string;
          proposal_version: number;
          state: Database["public"]["Enums"]["risk_check_state"];
          trade_proposal_id: string;
        };
        Update: {
          actual?: string;
          created_at?: string;
          explanation?: string | null;
          hard?: boolean;
          id?: string;
          key?: string;
          label_en?: string;
          label_th?: string;
          limit_value?: string | null;
          ordinal?: number;
          owner_id?: string;
          proposal_version?: number;
          state?: Database["public"]["Enums"]["risk_check_state"];
          trade_proposal_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "risk_checks_trade_proposal_id_owner_id_proposal_version_fkey";
            columns: ["trade_proposal_id", "owner_id", "proposal_version"];
            isOneToOne: false;
            referencedRelation: "trade_proposals";
            referencedColumns: ["id", "owner_id", "proposal_version"];
          },
        ];
      };
      risk_policies: {
        Row: {
          active_version_id: string | null;
          created_at: string;
          id: string;
          owner_id: string;
          policy_key: string;
          resource_version: number;
          trading_account_id: string;
          updated_at: string;
        };
        Insert: {
          active_version_id?: string | null;
          created_at?: string;
          id?: string;
          owner_id: string;
          policy_key: string;
          resource_version?: number;
          trading_account_id: string;
          updated_at?: string;
        };
        Update: {
          active_version_id?: string | null;
          created_at?: string;
          id?: string;
          owner_id?: string;
          policy_key?: string;
          resource_version?: number;
          trading_account_id?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "risk_policies_active_version_owner_fk";
            columns: ["active_version_id", "id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "risk_policy_versions";
            referencedColumns: ["id", "risk_policy_id", "owner_id"];
          },
          {
            foreignKeyName: "risk_policies_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      risk_policy_versions: {
        Row: {
          automatic_retry_on_broker_reject: boolean;
          averaging_down_allowed: boolean;
          canonical_symbol: string;
          created_at: string;
          created_by: string;
          created_by_type: Database["public"]["Enums"]["actor_type"];
          daily_loss_limit_pct: number;
          entry_tolerance_points: number;
          environment: string;
          grid_trading_allowed: boolean;
          id: string;
          loss_based_volume_increase_allowed: boolean;
          martingale_allowed: boolean;
          maximum_drawdown_pct: number;
          maximum_open_positions: number;
          maximum_permitted_volume: number;
          maximum_slippage_points: number;
          maximum_spread_points: number;
          maximum_trades_per_day: number;
          minimum_risk_reward: number;
          minimum_sample_size: number;
          news_blackout_minutes: number;
          owner_id: string;
          proposal_expiry_seconds: number;
          reason: string;
          require_calibrated_model: boolean;
          risk_per_trade_pct: number;
          risk_policy_id: string;
          source_command_id: string | null;
          spread_warning_points: number;
          stale_data_max_age_seconds: number;
          stop_loss_required: boolean;
          trading_account_id: string;
          version: number;
          version_label: string;
          weekly_loss_limit_pct: number;
        };
        Insert: {
          automatic_retry_on_broker_reject?: boolean;
          averaging_down_allowed?: boolean;
          canonical_symbol?: string;
          created_at?: string;
          created_by: string;
          created_by_type: Database["public"]["Enums"]["actor_type"];
          daily_loss_limit_pct?: number;
          entry_tolerance_points?: number;
          environment?: string;
          grid_trading_allowed?: boolean;
          id?: string;
          loss_based_volume_increase_allowed?: boolean;
          martingale_allowed?: boolean;
          maximum_drawdown_pct?: number;
          maximum_open_positions?: number;
          maximum_permitted_volume?: number;
          maximum_slippage_points?: number;
          maximum_spread_points?: number;
          maximum_trades_per_day?: number;
          minimum_risk_reward?: number;
          minimum_sample_size?: number;
          news_blackout_minutes?: number;
          owner_id: string;
          proposal_expiry_seconds?: number;
          reason: string;
          require_calibrated_model?: boolean;
          risk_per_trade_pct?: number;
          risk_policy_id: string;
          source_command_id?: string | null;
          spread_warning_points?: number;
          stale_data_max_age_seconds?: number;
          stop_loss_required?: boolean;
          trading_account_id: string;
          version: number;
          version_label: string;
          weekly_loss_limit_pct?: number;
        };
        Update: {
          automatic_retry_on_broker_reject?: boolean;
          averaging_down_allowed?: boolean;
          canonical_symbol?: string;
          created_at?: string;
          created_by?: string;
          created_by_type?: Database["public"]["Enums"]["actor_type"];
          daily_loss_limit_pct?: number;
          entry_tolerance_points?: number;
          environment?: string;
          grid_trading_allowed?: boolean;
          id?: string;
          loss_based_volume_increase_allowed?: boolean;
          martingale_allowed?: boolean;
          maximum_drawdown_pct?: number;
          maximum_open_positions?: number;
          maximum_permitted_volume?: number;
          maximum_slippage_points?: number;
          maximum_spread_points?: number;
          maximum_trades_per_day?: number;
          minimum_risk_reward?: number;
          minimum_sample_size?: number;
          news_blackout_minutes?: number;
          owner_id?: string;
          proposal_expiry_seconds?: number;
          reason?: string;
          require_calibrated_model?: boolean;
          risk_per_trade_pct?: number;
          risk_policy_id?: string;
          source_command_id?: string | null;
          spread_warning_points?: number;
          stale_data_max_age_seconds?: number;
          stop_loss_required?: boolean;
          trading_account_id?: string;
          version?: number;
          version_label?: string;
          weekly_loss_limit_pct?: number;
        };
        Relationships: [
          {
            foreignKeyName: "risk_policy_versions_risk_policy_id_owner_id_trading_accou_fkey";
            columns: ["risk_policy_id", "owner_id", "trading_account_id"];
            isOneToOne: false;
            referencedRelation: "risk_policies";
            referencedColumns: ["id", "owner_id", "trading_account_id"];
          },
          {
            foreignKeyName: "risk_policy_versions_source_command_owner_fk";
            columns: ["source_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_command_read_models";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "risk_policy_versions_source_command_owner_fk";
            columns: ["source_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_commands";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      system_command_events: {
        Row: {
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at: string;
          event_type: Database["public"]["Enums"]["command_event_type"];
          from_status:
            Database["public"]["Enums"]["system_command_status"] | null;
          id: string;
          message: string | null;
          metadata: Json;
          owner_id: string;
          result_code: string | null;
          sequence: number;
          system_command_id: string;
          to_status:
            Database["public"]["Enums"]["system_command_status"] | null;
        };
        Insert: {
          actor_id: string;
          actor_type: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          event_type: Database["public"]["Enums"]["command_event_type"];
          from_status?:
            Database["public"]["Enums"]["system_command_status"] | null;
          id?: string;
          message?: string | null;
          metadata?: Json;
          owner_id: string;
          result_code?: string | null;
          sequence: number;
          system_command_id: string;
          to_status?:
            Database["public"]["Enums"]["system_command_status"] | null;
        };
        Update: {
          actor_id?: string;
          actor_type?: Database["public"]["Enums"]["actor_type"];
          created_at?: string;
          event_type?: Database["public"]["Enums"]["command_event_type"];
          from_status?:
            Database["public"]["Enums"]["system_command_status"] | null;
          id?: string;
          message?: string | null;
          metadata?: Json;
          owner_id?: string;
          result_code?: string | null;
          sequence?: number;
          system_command_id?: string;
          to_status?:
            Database["public"]["Enums"]["system_command_status"] | null;
        };
        Relationships: [
          {
            foreignKeyName: "system_command_events_system_command_id_owner_id_fkey";
            columns: ["system_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_command_read_models";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "system_command_events_system_command_id_owner_id_fkey";
            columns: ["system_command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_commands";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      system_commands: {
        Row: {
          attempt_count: number;
          claimed_at: string | null;
          claimed_by: string | null;
          command_version: number;
          completed_at: string | null;
          created_at: string;
          event_sequence: number;
          expected_resource_version: number | null;
          expires_at: string;
          id: string;
          idempotency_key: string;
          last_error: string | null;
          lease_expires_at: string | null;
          lease_token: string | null;
          maximum_attempts: number;
          next_retry_at: string | null;
          owner_id: string;
          payload: Json;
          payload_schema_version: number;
          priority: number;
          requested_at: string;
          requested_by: string;
          result_code: string | null;
          result_message: string | null;
          status: Database["public"]["Enums"]["system_command_status"];
          target_resource_id: string | null;
          target_resource_type: string | null;
          type: Database["public"]["Enums"]["system_command_type"];
          updated_at: string;
        };
        Insert: {
          attempt_count?: number;
          claimed_at?: string | null;
          claimed_by?: string | null;
          command_version?: number;
          completed_at?: string | null;
          created_at?: string;
          event_sequence?: number;
          expected_resource_version?: number | null;
          expires_at: string;
          id?: string;
          idempotency_key: string;
          last_error?: string | null;
          lease_expires_at?: string | null;
          lease_token?: string | null;
          maximum_attempts?: number;
          next_retry_at?: string | null;
          owner_id: string;
          payload: Json;
          payload_schema_version?: number;
          priority?: number;
          requested_at?: string;
          requested_by: string;
          result_code?: string | null;
          result_message?: string | null;
          status?: Database["public"]["Enums"]["system_command_status"];
          target_resource_id?: string | null;
          target_resource_type?: string | null;
          type: Database["public"]["Enums"]["system_command_type"];
          updated_at?: string;
        };
        Update: {
          attempt_count?: number;
          claimed_at?: string | null;
          claimed_by?: string | null;
          command_version?: number;
          completed_at?: string | null;
          created_at?: string;
          event_sequence?: number;
          expected_resource_version?: number | null;
          expires_at?: string;
          id?: string;
          idempotency_key?: string;
          last_error?: string | null;
          lease_expires_at?: string | null;
          lease_token?: string | null;
          maximum_attempts?: number;
          next_retry_at?: string | null;
          owner_id?: string;
          payload?: Json;
          payload_schema_version?: number;
          priority?: number;
          requested_at?: string;
          requested_by?: string;
          result_code?: string | null;
          result_message?: string | null;
          status?: Database["public"]["Enums"]["system_command_status"];
          target_resource_id?: string | null;
          target_resource_type?: string | null;
          type?: Database["public"]["Enums"]["system_command_type"];
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "system_commands_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "system_commands_requested_by_fkey";
            columns: ["requested_by"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      system_components: {
        Row: {
          code: string;
          created_at: string;
          enabled: boolean;
          expected_heartbeat_seconds: number | null;
          id: string;
          label_th: string;
          owner_id: string;
          plane: Database["public"]["Enums"]["system_plane"];
        };
        Insert: {
          code: string;
          created_at?: string;
          enabled?: boolean;
          expected_heartbeat_seconds?: number | null;
          id?: string;
          label_th: string;
          owner_id: string;
          plane: Database["public"]["Enums"]["system_plane"];
        };
        Update: {
          code?: string;
          created_at?: string;
          enabled?: boolean;
          expected_heartbeat_seconds?: number | null;
          id?: string;
          label_th?: string;
          owner_id?: string;
          plane?: Database["public"]["Enums"]["system_plane"];
        };
        Relationships: [
          {
            foreignKeyName: "system_components_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      system_heartbeats: {
        Row: {
          created_at: string;
          detail: string;
          expires_at: string;
          id: string;
          observed_at: string;
          owner_id: string;
          state: Database["public"]["Enums"]["system_health_state"];
          system_component_id: string;
          updated_at: string;
          version: number;
          worker_id: string;
        };
        Insert: {
          created_at?: string;
          detail: string;
          expires_at: string;
          id?: string;
          observed_at: string;
          owner_id: string;
          state: Database["public"]["Enums"]["system_health_state"];
          system_component_id: string;
          updated_at?: string;
          version?: number;
          worker_id: string;
        };
        Update: {
          created_at?: string;
          detail?: string;
          expires_at?: string;
          id?: string;
          observed_at?: string;
          owner_id?: string;
          state?: Database["public"]["Enums"]["system_health_state"];
          system_component_id?: string;
          updated_at?: string;
          version?: number;
          worker_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "system_heartbeats_system_component_id_owner_id_fkey";
            columns: ["system_component_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_components";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      system_incidents: {
        Row: {
          code: string;
          created_at: string;
          detail: string;
          id: string;
          occurred_at: string;
          owner_id: string;
          reported_by_worker_id: string;
          request_id: string | null;
          resolved_at: string | null;
          severity: Database["public"]["Enums"]["incident_severity"];
          status: Database["public"]["Enums"]["incident_status"];
          title: string;
        };
        Insert: {
          code: string;
          created_at?: string;
          detail: string;
          id?: string;
          occurred_at: string;
          owner_id: string;
          reported_by_worker_id: string;
          request_id?: string | null;
          resolved_at?: string | null;
          severity: Database["public"]["Enums"]["incident_severity"];
          status?: Database["public"]["Enums"]["incident_status"];
          title: string;
        };
        Update: {
          code?: string;
          created_at?: string;
          detail?: string;
          id?: string;
          occurred_at?: string;
          owner_id?: string;
          reported_by_worker_id?: string;
          request_id?: string | null;
          resolved_at?: string | null;
          severity?: Database["public"]["Enums"]["incident_severity"];
          status?: Database["public"]["Enums"]["incident_status"];
          title?: string;
        };
        Relationships: [
          {
            foreignKeyName: "system_incidents_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      trade_decisions: {
        Row: {
          command_id: string;
          created_at: string;
          decided_at: string;
          decided_by: string;
          decision: Database["public"]["Enums"]["trade_decision_kind"];
          id: string;
          owner_id: string;
          proposal_version: number;
          reason: string | null;
          trade_proposal_id: string;
        };
        Insert: {
          command_id: string;
          created_at?: string;
          decided_at?: string;
          decided_by: string;
          decision: Database["public"]["Enums"]["trade_decision_kind"];
          id?: string;
          owner_id: string;
          proposal_version: number;
          reason?: string | null;
          trade_proposal_id: string;
        };
        Update: {
          command_id?: string;
          created_at?: string;
          decided_at?: string;
          decided_by?: string;
          decision?: Database["public"]["Enums"]["trade_decision_kind"];
          id?: string;
          owner_id?: string;
          proposal_version?: number;
          reason?: string | null;
          trade_proposal_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "trade_decisions_command_owner_fk";
            columns: ["command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_command_read_models";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "trade_decisions_command_owner_fk";
            columns: ["command_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "system_commands";
            referencedColumns: ["id", "owner_id"];
          },
          {
            foreignKeyName: "trade_decisions_decided_by_fkey";
            columns: ["decided_by"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "trade_decisions_trade_proposal_id_owner_id_proposal_versio_fkey";
            columns: ["trade_proposal_id", "owner_id", "proposal_version"];
            isOneToOne: false;
            referencedRelation: "trade_proposals";
            referencedColumns: ["id", "owner_id", "proposal_version"];
          },
        ];
      };
      trade_executions: {
        Row: {
          broker_deal_reference: string;
          broker_order_id: string;
          commission: number;
          created_at: string;
          executed_at: string;
          execution_kind: Database["public"]["Enums"]["broker_execution_kind"];
          id: string;
          owner_id: string;
          price: number;
          swap: number;
          volume: number;
        };
        Insert: {
          broker_deal_reference: string;
          broker_order_id: string;
          commission?: number;
          created_at?: string;
          executed_at: string;
          execution_kind: Database["public"]["Enums"]["broker_execution_kind"];
          id?: string;
          owner_id: string;
          price: number;
          swap?: number;
          volume: number;
        };
        Update: {
          broker_deal_reference?: string;
          broker_order_id?: string;
          commission?: number;
          created_at?: string;
          executed_at?: string;
          execution_kind?: Database["public"]["Enums"]["broker_execution_kind"];
          id?: string;
          owner_id?: string;
          price?: number;
          swap?: number;
          volume?: number;
        };
        Relationships: [
          {
            foreignKeyName: "trade_executions_broker_order_id_owner_id_fkey";
            columns: ["broker_order_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "broker_orders";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      trade_proposals: {
        Row: {
          account_currency: string;
          account_type: string;
          approved_volume: number | null;
          broker_server: string;
          broker_symbol: string;
          broker_symbol_id: string;
          calculated_volume: number;
          canonical_symbol: string;
          created_at: string;
          decision_trace_id: string;
          direction: Database["public"]["Enums"]["trade_direction"];
          eligibility_evaluated_at: string;
          eligibility_outcome: Database["public"]["Enums"]["eligibility_outcome"];
          eligibility_policy_id: string;
          eligibility_policy_version: string;
          entry_price: number;
          expires_at: string;
          feature_snapshot_id: string;
          id: string;
          market_snapshot_id: string;
          maximum_permitted_volume: number;
          model_version: string | null;
          owner_id: string;
          processed_at: string | null;
          proposal_version: number;
          requested_volume: number | null;
          risk_amount: number;
          risk_pct: number;
          risk_policy_version: string;
          risk_policy_version_id: string;
          risk_reward: number;
          status: Database["public"]["Enums"]["trade_proposal_status"];
          stop_loss_price: number;
          strategy_code: string;
          strategy_version: string;
          symbol_specification_version: string;
          take_profit_price: number;
          trading_account_id: string;
          updated_at: string;
        };
        Insert: {
          account_currency: string;
          account_type?: string;
          approved_volume?: number | null;
          broker_server: string;
          broker_symbol: string;
          broker_symbol_id: string;
          calculated_volume: number;
          canonical_symbol?: string;
          created_at?: string;
          decision_trace_id: string;
          direction: Database["public"]["Enums"]["trade_direction"];
          eligibility_evaluated_at: string;
          eligibility_outcome: Database["public"]["Enums"]["eligibility_outcome"];
          eligibility_policy_id: string;
          eligibility_policy_version: string;
          entry_price: number;
          expires_at: string;
          feature_snapshot_id: string;
          id?: string;
          market_snapshot_id: string;
          maximum_permitted_volume?: number;
          model_version?: string | null;
          owner_id: string;
          processed_at?: string | null;
          proposal_version: number;
          requested_volume?: number | null;
          risk_amount: number;
          risk_pct: number;
          risk_policy_version: string;
          risk_policy_version_id: string;
          risk_reward: number;
          status: Database["public"]["Enums"]["trade_proposal_status"];
          stop_loss_price: number;
          strategy_code: string;
          strategy_version: string;
          symbol_specification_version: string;
          take_profit_price: number;
          trading_account_id: string;
          updated_at?: string;
        };
        Update: {
          account_currency?: string;
          account_type?: string;
          approved_volume?: number | null;
          broker_server?: string;
          broker_symbol?: string;
          broker_symbol_id?: string;
          calculated_volume?: number;
          canonical_symbol?: string;
          created_at?: string;
          decision_trace_id?: string;
          direction?: Database["public"]["Enums"]["trade_direction"];
          eligibility_evaluated_at?: string;
          eligibility_outcome?: Database["public"]["Enums"]["eligibility_outcome"];
          eligibility_policy_id?: string;
          eligibility_policy_version?: string;
          entry_price?: number;
          expires_at?: string;
          feature_snapshot_id?: string;
          id?: string;
          market_snapshot_id?: string;
          maximum_permitted_volume?: number;
          model_version?: string | null;
          owner_id?: string;
          processed_at?: string | null;
          proposal_version?: number;
          requested_volume?: number | null;
          risk_amount?: number;
          risk_pct?: number;
          risk_policy_version?: string;
          risk_policy_version_id?: string;
          risk_reward?: number;
          status?: Database["public"]["Enums"]["trade_proposal_status"];
          stop_loss_price?: number;
          strategy_code?: string;
          strategy_version?: string;
          symbol_specification_version?: string;
          take_profit_price?: number;
          trading_account_id?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "trade_proposals_broker_symbol_id_owner_id_trading_account__fkey";
            columns: [
              "broker_symbol_id",
              "owner_id",
              "trading_account_id",
              "symbol_specification_version",
            ];
            isOneToOne: false;
            referencedRelation: "broker_symbols";
            referencedColumns: [
              "id",
              "owner_id",
              "trading_account_id",
              "specification_version",
            ];
          },
          {
            foreignKeyName: "trade_proposals_feature_snapshot_id_owner_id_trading_accou_fkey";
            columns: [
              "feature_snapshot_id",
              "owner_id",
              "trading_account_id",
              "market_snapshot_id",
            ];
            isOneToOne: false;
            referencedRelation: "feature_snapshots";
            referencedColumns: [
              "id",
              "owner_id",
              "trading_account_id",
              "market_snapshot_id",
            ];
          },
          {
            foreignKeyName: "trade_proposals_market_snapshot_id_owner_id_trading_accoun_fkey";
            columns: ["market_snapshot_id", "owner_id", "trading_account_id"];
            isOneToOne: false;
            referencedRelation: "market_snapshots";
            referencedColumns: ["id", "owner_id", "trading_account_id"];
          },
          {
            foreignKeyName: "trade_proposals_risk_policy_version_id_owner_id_risk_polic_fkey";
            columns: [
              "risk_policy_version_id",
              "owner_id",
              "risk_policy_version",
              "trading_account_id",
            ];
            isOneToOne: false;
            referencedRelation: "risk_policy_versions";
            referencedColumns: [
              "id",
              "owner_id",
              "version_label",
              "trading_account_id",
            ];
          },
          {
            foreignKeyName: "trade_proposals_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
      trading_accounts: {
        Row: {
          account_currency: string;
          account_type: string;
          broker_account_reference: string;
          broker_server: string;
          created_at: string;
          environment: string;
          id: string;
          maximum_open_positions: number;
          maximum_permitted_volume: number;
          owner_id: string;
          stop_loss_required: boolean;
          updated_at: string;
          verification_state: string;
          version: number;
        };
        Insert: {
          account_currency?: string;
          account_type?: string;
          broker_account_reference: string;
          broker_server: string;
          created_at?: string;
          environment?: string;
          id?: string;
          maximum_open_positions?: number;
          maximum_permitted_volume?: number;
          owner_id: string;
          stop_loss_required?: boolean;
          updated_at?: string;
          verification_state?: string;
          version?: number;
        };
        Update: {
          account_currency?: string;
          account_type?: string;
          broker_account_reference?: string;
          broker_server?: string;
          created_at?: string;
          environment?: string;
          id?: string;
          maximum_open_positions?: number;
          maximum_permitted_volume?: number;
          owner_id?: string;
          stop_loss_required?: boolean;
          updated_at?: string;
          verification_state?: string;
          version?: number;
        };
        Relationships: [
          {
            foreignKeyName: "trading_accounts_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      trading_modes: {
        Row: {
          created_at: string;
          id: string;
          mode: string;
          owner_id: string;
          state_reason: string | null;
          system_state: Database["public"]["Enums"]["runtime_system_state"];
          trading_account_id: string;
          updated_at: string;
          version: number;
        };
        Insert: {
          created_at?: string;
          id?: string;
          mode?: string;
          owner_id: string;
          state_reason?: string | null;
          system_state?: Database["public"]["Enums"]["runtime_system_state"];
          trading_account_id: string;
          updated_at?: string;
          version?: number;
        };
        Update: {
          created_at?: string;
          id?: string;
          mode?: string;
          owner_id?: string;
          state_reason?: string | null;
          system_state?: Database["public"]["Enums"]["runtime_system_state"];
          trading_account_id?: string;
          updated_at?: string;
          version?: number;
        };
        Relationships: [
          {
            foreignKeyName: "trading_modes_trading_account_id_owner_id_fkey";
            columns: ["trading_account_id", "owner_id"];
            isOneToOne: false;
            referencedRelation: "trading_accounts";
            referencedColumns: ["id", "owner_id"];
          },
        ];
      };
    };
    Views: {
      system_command_read_models: {
        Row: {
          attempt_count: number | null;
          claimed_at: string | null;
          claimed_by: string | null;
          command_version: number | null;
          completed_at: string | null;
          created_at: string | null;
          event_sequence: number | null;
          expected_resource_version: number | null;
          expires_at: string | null;
          id: string | null;
          idempotency_key: string | null;
          lease_expires_at: string | null;
          maximum_attempts: number | null;
          next_retry_at: string | null;
          owner_id: string | null;
          payload_schema_version: number | null;
          priority: number | null;
          requested_at: string | null;
          requested_by: string | null;
          result_code: string | null;
          result_message: string | null;
          status: Database["public"]["Enums"]["system_command_status"] | null;
          target_resource_id: string | null;
          target_resource_type: string | null;
          type: Database["public"]["Enums"]["system_command_type"] | null;
          updated_at: string | null;
        };
        Insert: {
          attempt_count?: number | null;
          claimed_at?: string | null;
          claimed_by?: string | null;
          command_version?: number | null;
          completed_at?: string | null;
          created_at?: string | null;
          event_sequence?: number | null;
          expected_resource_version?: number | null;
          expires_at?: string | null;
          id?: string | null;
          idempotency_key?: string | null;
          lease_expires_at?: string | null;
          maximum_attempts?: number | null;
          next_retry_at?: string | null;
          owner_id?: string | null;
          payload_schema_version?: number | null;
          priority?: number | null;
          requested_at?: string | null;
          requested_by?: string | null;
          result_code?: string | null;
          result_message?: string | null;
          status?: Database["public"]["Enums"]["system_command_status"] | null;
          target_resource_id?: string | null;
          target_resource_type?: string | null;
          type?: Database["public"]["Enums"]["system_command_type"] | null;
          updated_at?: string | null;
        };
        Update: {
          attempt_count?: number | null;
          claimed_at?: string | null;
          claimed_by?: string | null;
          command_version?: number | null;
          completed_at?: string | null;
          created_at?: string | null;
          event_sequence?: number | null;
          expected_resource_version?: number | null;
          expires_at?: string | null;
          id?: string | null;
          idempotency_key?: string | null;
          lease_expires_at?: string | null;
          maximum_attempts?: number | null;
          next_retry_at?: string | null;
          owner_id?: string | null;
          payload_schema_version?: number | null;
          priority?: number | null;
          requested_at?: string | null;
          requested_by?: string | null;
          result_code?: string | null;
          result_message?: string | null;
          status?: Database["public"]["Enums"]["system_command_status"] | null;
          target_resource_id?: string | null;
          target_resource_type?: string | null;
          type?: Database["public"]["Enums"]["system_command_type"] | null;
          updated_at?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "system_commands_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "system_commands_requested_by_fkey";
            columns: ["requested_by"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
    };
    Functions: {
      request_emergency_stop: {
        Args: {
          command_expires_at?: string;
          idempotency_key: string;
          reason: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_pause_new_trades: {
        Args: {
          command_expires_at?: string;
          idempotency_key: string;
          reason?: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_position_close: {
        Args: {
          command_expires_at?: string;
          expected_position_version: number;
          idempotency_key: string;
          position_id: string;
          reason: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_proposal_approval: {
        Args: {
          approval_session_id?: string;
          command_expires_at?: string;
          idempotency_key: string;
          proposal_id: string;
          proposal_version: number;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_proposal_rejection: {
        Args: {
          command_expires_at?: string;
          idempotency_key: string;
          proposal_id: string;
          proposal_version: number;
          reason: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_resume_system: {
        Args: {
          checklist_acknowledgement_id: string;
          command_expires_at?: string;
          idempotency_key: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_risk_policy_change: {
        Args: {
          command_expires_at?: string;
          expected_policy_version: number;
          idempotency_key: string;
          new_value: number;
          reason: string;
          rule_key: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_stop_loss_change: {
        Args: {
          command_expires_at?: string;
          expected_position_version: number;
          idempotency_key: string;
          new_stop_loss: number;
          position_id: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      request_take_profit_change: {
        Args: {
          command_expires_at?: string;
          expected_position_version: number;
          idempotency_key: string;
          new_take_profit: number;
          position_id: string;
        };
        Returns: Database["public"]["CompositeTypes"]["command_action_result"];
        SetofOptions: {
          from: "*";
          to: "command_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_begin_reconciliation: { Args: { report: Json }; Returns: string };
      worker_claim_next_command: {
        Args: { lease_seconds?: number };
        Returns: Database["public"]["CompositeTypes"]["worker_claim_result"];
        SetofOptions: {
          from: "*";
          to: "worker_claim_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_complete_command: {
        Args: {
          command_id: string;
          lease_token: string;
          result_code: string;
          result_message?: string;
        };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_complete_reconciliation: {
        Args: { report: Json };
        Returns: string;
      };
      worker_fail_command: {
        Args: {
          command_id: string;
          last_error: string;
          lease_token: string;
          next_retry_at?: string;
          result_code: string;
          result_message: string;
          retryable?: boolean;
        };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_mark_command_executing: {
        Args: { command_id: string; lease_token: string };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_mark_command_validating: {
        Args: { command_id: string; lease_token: string };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_read_mt5_reconciliation_state: { Args: never; Returns: Json };
      worker_record_heartbeat: {
        Args: {
          component_code: string;
          detail: string;
          observed_at: string;
          state: Database["public"]["Enums"]["system_health_state"];
          valid_for_seconds?: number;
        };
        Returns: string;
      };
      worker_record_incident: {
        Args: {
          code: string;
          detail: string;
          occurred_at: string;
          request_id?: string;
          severity: Database["public"]["Enums"]["incident_severity"];
          title: string;
        };
        Returns: Database["public"]["CompositeTypes"]["worker_incident_result"];
        SetofOptions: {
          from: "*";
          to: "worker_incident_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_record_mt5_account_observation: {
        Args: { observation: Json };
        Returns: string;
      };
      worker_record_mt5_symbol_observation: {
        Args: { observation: Json };
        Returns: string;
      };
      worker_record_reconciliation_mismatch: {
        Args: { mismatch: Json; reconciliation_id: string };
        Returns: string;
      };
      worker_reject_command: {
        Args: {
          command_id: string;
          lease_token: string;
          result_code: string;
          result_message?: string;
        };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_renew_command_lease: {
        Args: {
          command_id: string;
          lease_seconds?: number;
          lease_token: string;
        };
        Returns: Database["public"]["CompositeTypes"]["worker_action_result"];
        SetofOptions: {
          from: "*";
          to: "worker_action_result";
          isOneToOne: true;
          isSetofReturn: false;
        };
      };
      worker_upsert_mt5_latest_tick: {
        Args: { observation: Json };
        Returns: string;
      };
    };
    Enums: {
      actor_type: "user" | "worker" | "system";
      broker_execution_kind:
        "open" | "close" | "stop_loss_change" | "take_profit_change";
      broker_order_status:
        | "recorded"
        | "submitted"
        | "accepted"
        | "rejected"
        | "cancelled"
        | "failed";
      command_event_type:
        | "created"
        | "claimed"
        | "claim_recovered"
        | "lease_renewed"
        | "status_changed"
        | "retry_scheduled";
      eligibility_outcome: "auto" | "ask" | "block";
      incident_severity: "critical" | "warning" | "info";
      incident_status: "open" | "resolved";
      market_freshness: "live" | "delayed" | "stale";
      market_regime: "trending" | "range" | "high_volatility" | "news_risk";
      market_session: "asia" | "london" | "newyork" | "overlap";
      market_transport: "realtime_broadcast" | "database_fallback";
      position_event_type:
        "observed" | "status_changed" | "mismatch_detected" | "reconciled";
      position_status:
        "open" | "close_requested" | "closing" | "closed" | "mismatch";
      risk_check_state: "pass" | "warn" | "fail" | "na";
      runtime_system_state:
        "running" | "paused" | "emergency_stop" | "recovering";
      system_command_status:
        | "pending"
        | "claimed"
        | "validating"
        | "executing"
        | "succeeded"
        | "rejected"
        | "failed"
        | "expired"
        | "cancelled";
      system_command_type:
        | "APPROVE_PROPOSAL"
        | "REJECT_PROPOSAL"
        | "PAUSE_NEW_TRADES"
        | "RESUME_SYSTEM"
        | "ACTIVATE_EMERGENCY_STOP"
        | "REQUEST_POSITION_CLOSE"
        | "REQUEST_STOP_LOSS_CHANGE"
        | "REQUEST_TAKE_PROFIT_CHANGE"
        | "REQUEST_RISK_POLICY_CHANGE";
      system_health_state:
        "healthy" | "degraded" | "warning" | "failed" | "unknown";
      system_plane: "control_plane" | "execution_plane";
      trade_decision_kind: "approve" | "reject";
      trade_direction: "BUY" | "SELL";
      trade_proposal_status:
        | "candidate"
        | "validated"
        | "pending_approval"
        | "approved"
        | "rejected"
        | "blocked"
        | "expired"
        | "execution_pending"
        | "executed"
        | "failed";
    };
    CompositeTypes: {
      command_action_result: {
        accepted: boolean | null;
        command_id: string | null;
        created: boolean | null;
        status: Database["public"]["Enums"]["system_command_status"] | null;
        result_code: string | null;
      };
      worker_action_result: {
        accepted: boolean | null;
        command_id: string | null;
        status: Database["public"]["Enums"]["system_command_status"] | null;
        command_version: number | null;
        result_code: string | null;
      };
      worker_claim_result: {
        accepted: boolean | null;
        command_id: string | null;
        status: Database["public"]["Enums"]["system_command_status"] | null;
        lease_token: string | null;
        lease_expires_at: string | null;
        command_version: number | null;
        result_code: string | null;
      };
      worker_incident_result: {
        accepted: boolean | null;
        incident_id: string | null;
        created: boolean | null;
        result_code: string | null;
      };
    };
  };
};

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">;

type DefaultSchema = DatabaseWithoutInternals[Extract<
  keyof Database,
  "public"
>];

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R;
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R;
      }
      ? R
      : never
    : never;

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I;
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I;
      }
      ? I
      : never
    : never;

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U;
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U;
      }
      ? U
      : never
    : never;

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    keyof DefaultSchema["Enums"] | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never;

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never;

export const Constants = {
  public: {
    Enums: {
      actor_type: ["user", "worker", "system"],
      broker_execution_kind: [
        "open",
        "close",
        "stop_loss_change",
        "take_profit_change",
      ],
      broker_order_status: [
        "recorded",
        "submitted",
        "accepted",
        "rejected",
        "cancelled",
        "failed",
      ],
      command_event_type: [
        "created",
        "claimed",
        "claim_recovered",
        "lease_renewed",
        "status_changed",
        "retry_scheduled",
      ],
      eligibility_outcome: ["auto", "ask", "block"],
      incident_severity: ["critical", "warning", "info"],
      incident_status: ["open", "resolved"],
      market_freshness: ["live", "delayed", "stale"],
      market_regime: ["trending", "range", "high_volatility", "news_risk"],
      market_session: ["asia", "london", "newyork", "overlap"],
      market_transport: ["realtime_broadcast", "database_fallback"],
      position_event_type: [
        "observed",
        "status_changed",
        "mismatch_detected",
        "reconciled",
      ],
      position_status: [
        "open",
        "close_requested",
        "closing",
        "closed",
        "mismatch",
      ],
      risk_check_state: ["pass", "warn", "fail", "na"],
      runtime_system_state: [
        "running",
        "paused",
        "emergency_stop",
        "recovering",
      ],
      system_command_status: [
        "pending",
        "claimed",
        "validating",
        "executing",
        "succeeded",
        "rejected",
        "failed",
        "expired",
        "cancelled",
      ],
      system_command_type: [
        "APPROVE_PROPOSAL",
        "REJECT_PROPOSAL",
        "PAUSE_NEW_TRADES",
        "RESUME_SYSTEM",
        "ACTIVATE_EMERGENCY_STOP",
        "REQUEST_POSITION_CLOSE",
        "REQUEST_STOP_LOSS_CHANGE",
        "REQUEST_TAKE_PROFIT_CHANGE",
        "REQUEST_RISK_POLICY_CHANGE",
      ],
      system_health_state: [
        "healthy",
        "degraded",
        "warning",
        "failed",
        "unknown",
      ],
      system_plane: ["control_plane", "execution_plane"],
      trade_decision_kind: ["approve", "reject"],
      trade_direction: ["BUY", "SELL"],
      trade_proposal_status: [
        "candidate",
        "validated",
        "pending_approval",
        "approved",
        "rejected",
        "blocked",
        "expired",
        "execution_pending",
        "executed",
        "failed",
      ],
    },
  },
} as const;
