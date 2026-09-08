<?php
/**
 * Talent <-> Show many-to-many, including date-ranged substitute coverage
 * (Spec Section 4). A dedicated table rather than a postmeta array on Show:
 * "which shows is this user talent for" needs to be a normal indexed lookup
 * (Section 12's talent-scoped dashboard) rather than a meta_query LIKE-scan
 * across every Show's serialized meta.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Talent_Assignments {

	public static function table_name() {
		global $wpdb;
		return $wpdb->prefix . 'ng_talent_assignments';
	}

	public static function create_table() {
		global $wpdb;
		$table_name      = self::table_name();
		$charset_collate = $wpdb->get_charset_collate();

		$sql = "CREATE TABLE {$table_name} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			show_id BIGINT UNSIGNED NOT NULL,
			user_id BIGINT UNSIGNED NOT NULL,
			role VARCHAR(20) NOT NULL,
			start_date DATE NULL,
			end_date DATE NULL,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			PRIMARY KEY  (id),
			KEY show_id (show_id),
			KEY user_id (user_id)
		) {$charset_collate};";

		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		dbDelta( $sql );
	}

	/**
	 * Sets the show's primary talent, replacing any existing primary row.
	 * Reassignment is prospective-only (Spec 4.1): past episodes already
	 * snapshot their recording talent independently in ng_talent_user_id,
	 * so the old primary row can simply be replaced, not preserved.
	 */
	public static function set_primary( $show_id, $user_id ) {
		global $wpdb;
		$table = self::table_name();
		$wpdb->delete( $table, array( 'show_id' => $show_id, 'role' => 'primary' ), array( '%d', '%s' ) );
		$now = current_time( 'mysql' );
		$wpdb->insert(
			$table,
			array(
				'show_id'    => $show_id,
				'user_id'    => $user_id,
				'role'       => 'primary',
				'start_date' => null,
				'end_date'   => null,
				'created_at' => $now,
				'updated_at' => $now,
			),
			array( '%d', '%d', '%s', '%s', '%s', '%s', '%s' )
		);
		return $wpdb->insert_id;
	}

	public static function add_substitute( $show_id, $user_id, $start_date, $end_date ) {
		global $wpdb;
		$now = current_time( 'mysql' );
		$wpdb->insert(
			self::table_name(),
			array(
				'show_id'    => $show_id,
				'user_id'    => $user_id,
				'role'       => 'substitute',
				'start_date' => $start_date,
				'end_date'   => $end_date,
				'created_at' => $now,
				'updated_at' => $now,
			),
			array( '%d', '%d', '%s', '%s', '%s', '%s', '%s' )
		);
		return $wpdb->insert_id;
	}

	public static function remove( $assignment_id ) {
		global $wpdb;
		return (bool) $wpdb->delete( self::table_name(), array( 'id' => $assignment_id ), array( '%d' ) );
	}

	public static function get( $assignment_id ) {
		global $wpdb;
		$table = self::table_name();
		return $wpdb->get_row( $wpdb->prepare( "SELECT * FROM {$table} WHERE id = %d", $assignment_id ), ARRAY_A );
	}

	public static function list_for_show( $show_id ) {
		global $wpdb;
		$table = self::table_name();
		return $wpdb->get_results(
			$wpdb->prepare( "SELECT * FROM {$table} WHERE show_id = %d ORDER BY role ASC, start_date ASC", $show_id ),
			ARRAY_A
		);
	}

	public static function list_for_user( $user_id ) {
		global $wpdb;
		$table = self::table_name();
		return $wpdb->get_results(
			$wpdb->prepare( "SELECT * FROM {$table} WHERE user_id = %d ORDER BY show_id ASC", $user_id ),
			ARRAY_A
		);
	}

	/**
	 * The talent who should record/is covering a show on a given date: an
	 * active substitute for that date takes precedence over the primary.
	 */
	public static function get_effective_talent( $show_id, $date ) {
		$rows = self::list_for_show( $show_id );
		$primary_user_id = null;

		foreach ( $rows as $row ) {
			if ( 'primary' === $row['role'] ) {
				$primary_user_id = (int) $row['user_id'];
				continue;
			}
			if ( 'substitute' === $row['role'] && $row['start_date'] <= $date && $row['end_date'] >= $date ) {
				return (int) $row['user_id'];
			}
		}

		return $primary_user_id;
	}

	/** Is $user_id allowed to act on $show_id right now (primary, or covering today)? */
	public static function user_is_assigned_to_show( $user_id, $show_id ) {
		$today = current_time( 'Y-m-d' );
		foreach ( self::list_for_show( $show_id ) as $row ) {
			if ( (int) $row['user_id'] !== (int) $user_id ) {
				continue;
			}
			if ( 'primary' === $row['role'] ) {
				return true;
			}
			if ( 'substitute' === $row['role'] && $row['start_date'] <= $today && $row['end_date'] >= $today ) {
				return true;
			}
		}
		return false;
	}
}
