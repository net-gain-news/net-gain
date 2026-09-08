<?php
/**
 * Encrypted storage for genuine secrets (Spec Section 3.3) - kept in a
 * dedicated table, never postmeta, so they can never accidentally round-trip
 * through generic CPT REST meta exposure. Phase 1 only builds this storage
 * primitive plus the YouTube-OAuth stub routes; the actual OAuth redirect/
 * refresh flow is deferred to the YouTube build phase.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Secrets {

	const CIPHER = 'aes-256-cbc';

	public static function table_name() {
		global $wpdb;
		return $wpdb->prefix . 'ng_secrets';
	}

	public static function create_table() {
		global $wpdb;
		$table_name      = self::table_name();
		$charset_collate = $wpdb->get_charset_collate();

		$sql = "CREATE TABLE {$table_name} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			scope VARCHAR(20) NOT NULL,
			show_id BIGINT UNSIGNED NULL,
			secret_key VARCHAR(100) NOT NULL,
			ciphertext LONGTEXT NOT NULL,
			updated_at DATETIME NOT NULL,
			PRIMARY KEY  (id),
			UNIQUE KEY scope_show_key (scope, show_id, secret_key)
		) {$charset_collate};";

		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		dbDelta( $sql );
	}

	private static function is_configured() {
		return defined( 'NET_GAIN_ENCRYPTION_KEY' ) && '' !== NET_GAIN_ENCRYPTION_KEY;
	}

	private static function cipher_key() {
		// Fixed-length key for AES-256, derived from the wp-config.php constant -
		// same pattern as WP core's own AUTH_KEY/SECURE_AUTH_KEY.
		return hash( 'sha256', NET_GAIN_ENCRYPTION_KEY, true );
	}

	public static function set( $scope, $show_id, $secret_key, $plaintext ) {
		if ( ! self::is_configured() ) {
			return new WP_Error( 'ng_encryption_not_configured', 'NET_GAIN_ENCRYPTION_KEY is not defined in wp-config.php.' );
		}

		global $wpdb;
		$iv         = openssl_random_pseudo_bytes( openssl_cipher_iv_length( self::CIPHER ) );
		$ciphertext = openssl_encrypt( $plaintext, self::CIPHER, self::cipher_key(), OPENSSL_RAW_DATA, $iv );
		$stored     = base64_encode( $iv . $ciphertext );

		$wpdb->query(
			$wpdb->prepare(
				"INSERT INTO " . self::table_name() . " (scope, show_id, secret_key, ciphertext, updated_at)
				 VALUES (%s, %d, %s, %s, %s)
				 ON DUPLICATE KEY UPDATE ciphertext = VALUES(ciphertext), updated_at = VALUES(updated_at)",
				$scope,
				$show_id,
				$secret_key,
				$stored,
				current_time( 'mysql' )
			)
		);

		return true;
	}

	public static function get( $scope, $show_id, $secret_key ) {
		if ( ! self::is_configured() ) {
			return new WP_Error( 'ng_encryption_not_configured', 'NET_GAIN_ENCRYPTION_KEY is not defined in wp-config.php.' );
		}

		global $wpdb;
		$row = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT ciphertext FROM " . self::table_name() . " WHERE scope = %s AND show_id = %d AND secret_key = %s",
				$scope,
				$show_id,
				$secret_key
			)
		);

		if ( ! $row ) {
			return null;
		}

		$raw        = base64_decode( $row->ciphertext );
		$iv_length  = openssl_cipher_iv_length( self::CIPHER );
		$iv         = substr( $raw, 0, $iv_length );
		$ciphertext = substr( $raw, $iv_length );

		$plaintext = openssl_decrypt( $ciphertext, self::CIPHER, self::cipher_key(), OPENSSL_RAW_DATA, $iv );
		return false === $plaintext ? null : $plaintext;
	}

	public static function exists( $scope, $show_id, $secret_key ) {
		global $wpdb;
		$count = $wpdb->get_var(
			$wpdb->prepare(
				"SELECT COUNT(*) FROM " . self::table_name() . " WHERE scope = %s AND show_id = %d AND secret_key = %s",
				$scope,
				$show_id,
				$secret_key
			)
		);
		return $count > 0;
	}

	public static function delete( $scope, $show_id, $secret_key ) {
		global $wpdb;
		return (bool) $wpdb->delete(
			self::table_name(),
			array( 'scope' => $scope, 'show_id' => $show_id, 'secret_key' => $secret_key ),
			array( '%s', '%d', '%s' )
		);
	}
}
