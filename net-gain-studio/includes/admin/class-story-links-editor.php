<?php
/**
 * "Source stories" editor on the podcast (public episode page) edit screen.
 *
 * The page's source-stories list is read from the episode record's ng_story_links, and every website publish rebuilds that list from
 * the numbered link lines at the end of the episode's final script. Editing only the list would be undone by the next publish, so a
 * save here writes the list and the script lines (and the stored Captivate notes' link paragraphs) together.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Story_Links_Editor {

	const NONCE    = 'ng_story_links_nonce';
	const MAX_ROWS = 20;

	public static function register() {
		add_action( 'add_meta_boxes_podcast', array( __CLASS__, 'add_meta_box' ) );
		add_action( 'save_post_podcast', array( __CLASS__, 'save' ), 10, 2 );
		add_action( 'admin_notices', array( __CLASS__, 'notice' ) );
	}

	/* ----------------------------------------------------------------- pure helpers (no WordPress needed) */

	/**
	 * Turns the submitted rows into a clean list. Returns array( links, skipped ): rows with no address or an address that is not
	 * http(s) are dropped and counted. A row with an address but no caption is captioned with its site name.
	 */
	public static function clean_rows( $titles, $urls ) {
		$links   = array();
		$skipped = 0;
		$count   = max( count( (array) $titles ), count( (array) $urls ) );
		for ( $i = 0; $i < $count && count( $links ) < self::MAX_ROWS; $i++ ) {
			$title = isset( $titles[ $i ] ) && is_string( $titles[ $i ] ) ? $titles[ $i ] : '';
			$url   = isset( $urls[ $i ] ) && is_string( $urls[ $i ] ) ? trim( $urls[ $i ] ) : '';
			$title = trim( preg_replace( '/\s+/u', ' ', strip_tags( $title ) ) );
			$title = str_replace( '"', "'", $title );
			if ( '' === $title && '' === $url ) {
				continue;
			}
			if ( ! preg_match( '#^https?://[^\s<>"]+$#i', $url ) ) {
				$skipped++;
				continue;
			}
			if ( '' === $title ) {
				$host  = parse_url( $url, PHP_URL_HOST );
				$title = $host ? preg_replace( '/^www\./i', '', $host ) : $url;
			}
			$links[] = array(
				'title' => $title,
				'url'   => $url,
			);
		}
		return array( $links, $skipped );
	}

	/** The final script with its numbered link lines replaced by `$links` (renumbered, one address per line), nothing else touched. */
	public static function rewrite_script_links( $script, array $links ) {
		$lines = preg_split( '/\R/u', (string) $script );
		$new   = array();
		foreach ( $links as $n => $link ) {
			$new[] = ( $n + 1 ) . '. "' . $link['title'] . '" ' . "\u{2014}" . ' ' . $link['url'];
		}
		$out      = array();
		$inserted = false;
		foreach ( $lines as $line ) {
			if ( null !== Net_Gain_REST_Website_Publish::parse_link_line( $line ) ) {
				if ( ! $inserted ) {
					$out      = array_merge( $out, $new );
					$inserted = true;
				}
				continue;
			}
			$out[] = $line;
		}
		if ( ! $inserted && $new ) {
			$out[] = '';
			$out   = array_merge( $out, $new );
		}
		return implode( "\n", $out );
	}

	/** The stored Captivate notes with the paragraphs after "Stories & links:" replaced by `$links`; unchanged when that heading is absent. */
	public static function rewrite_notes_links( $notes, array $links ) {
		$marker = '<p><strong>Stories &amp; links:</strong></p>';
		$pos    = strpos( (string) $notes, $marker );
		if ( false === $pos ) {
			return $notes;
		}
		$html = '';
		foreach ( $links as $link ) {
			$html .= '<p>"' . htmlspecialchars( $link['title'], ENT_NOQUOTES, 'UTF-8' ) . '" ' . "\u{2014}" . ' <a href="' . htmlspecialchars( $link['url'], ENT_QUOTES, 'UTF-8' )
				. '" rel="nofollow">' . htmlspecialchars( $link['url'], ENT_NOQUOTES, 'UTF-8' ) . '</a></p>';
		}
		return substr( $notes, 0, $pos + strlen( $marker ) ) . $html;
	}

	/* ----------------------------------------------------------------- WordPress wiring */

	private static function episode_id( $post_id ) {
		return (int) get_post_meta( $post_id, '_ng_source_episode_id', true );
	}

	public static function add_meta_box( $post ) {
		add_meta_box( 'ng-story-links', 'Source stories', array( __CLASS__, 'render' ), 'podcast', 'normal', 'high' );
	}

	public static function render( $post ) {
		$episode_id = self::episode_id( $post->ID );
		if ( ! $episode_id ) {
			echo '<p>This page was not made by Net Gain Studio, so it has no source-stories list to edit here.</p>';
			return;
		}
		$links = get_post_meta( $episode_id, 'ng_story_links', true );
		$links = is_array( $links ) ? array_values( $links ) : array();
		if ( ! $links ) {
			$links = array(
				array(
					'title' => '',
					'url'   => '',
				),
			);
		}
		wp_nonce_field( 'ng_story_links_' . $post->ID, self::NONCE );
		?>
		<style>
			#ng-sl p.ng-sl-help{max-width:760px;color:#50575e;line-height:1.5;margin:0 0 12px}
			#ng-sl .ng-sl-row{display:flex;gap:6px;align-items:center;margin:0 0 6px}
			#ng-sl .ng-sl-n{width:22px;text-align:right;color:#787c82}
			#ng-sl .ng-sl-t{flex:2 1 0;min-width:0}
			#ng-sl .ng-sl-u{flex:3 1 0;min-width:0}
			#ng-sl .ng-sl-row .button{padding:0 8px;min-height:30px}
		</style>
		<div id="ng-sl">
			<input type="hidden" name="ng_story_links_present" value="1">
			<p class="ng-sl-help">The list shown under “Source stories” on the page, in this order: the story people hear first goes first. Each row is a caption and the address it links to. Press <strong>Update</strong> to save. The same links are written into the episode’s script record so the next publish keeps them. The Captivate show notes, the YouTube description and emails already sent are separate and are not changed.</p>
			<div class="ng-sl-rows">
				<?php foreach ( $links as $link ) : ?>
					<div class="ng-sl-row">
						<span class="ng-sl-n"></span>
						<input type="text" class="ng-sl-t" name="ng_sl_title[]" value="<?php echo esc_attr( isset( $link['title'] ) ? $link['title'] : '' ); ?>" placeholder="Caption">
						<input type="url" class="ng-sl-u" name="ng_sl_url[]" value="<?php echo esc_attr( isset( $link['url'] ) ? $link['url'] : '' ); ?>" placeholder="https://…">
						<button type="button" class="button" data-act="up" title="Move up" aria-label="Move up">↑</button>
						<button type="button" class="button" data-act="down" title="Move down" aria-label="Move down">↓</button>
						<button type="button" class="button" data-act="remove" title="Remove" aria-label="Remove this story">×</button>
					</div>
				<?php endforeach; ?>
			</div>
			<p><button type="button" class="button" id="ng-sl-add">Add a story</button></p>
		</div>
		<script>
		(function(){
			var box=document.getElementById('ng-sl');if(!box)return;
			var rows=box.querySelector('.ng-sl-rows');
			function number(){[].forEach.call(rows.children,function(r,i){r.querySelector('.ng-sl-n').textContent=(i+1)+'.';});}
			function blank(){var r=rows.firstElementChild.cloneNode(true);[].forEach.call(r.querySelectorAll('input'),function(i){i.value='';});return r;}
			rows.addEventListener('click',function(e){
				var b=e.target.closest('button[data-act]');if(!b)return;
				var r=b.parentNode,act=b.getAttribute('data-act');
				if(act==='up'&&r.previousElementSibling)rows.insertBefore(r,r.previousElementSibling);
				if(act==='down'&&r.nextElementSibling)rows.insertBefore(r.nextElementSibling,r);
				if(act==='remove'){if(rows.children.length>1)rows.removeChild(r);else[].forEach.call(r.querySelectorAll('input'),function(i){i.value='';});}
				number();
			});
			document.getElementById('ng-sl-add').addEventListener('click',function(){var r=blank();rows.appendChild(r);number();r.querySelector('.ng-sl-t').focus();});
			number();
		})();
		</script>
		<?php
	}

	public static function save( $post_id, $post ) {
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}
		if ( empty( $_POST['ng_story_links_present'] ) || ! isset( $_POST[ self::NONCE ] ) ) {
			return;
		}
		if ( ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST[ self::NONCE ] ) ), 'ng_story_links_' . $post_id ) ) {
			return;
		}
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}
		$episode_id = self::episode_id( $post_id );
		if ( ! $episode_id ) {
			return;
		}
		$titles = isset( $_POST['ng_sl_title'] ) && is_array( $_POST['ng_sl_title'] ) ? wp_unslash( $_POST['ng_sl_title'] ) : array(); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		$urls   = isset( $_POST['ng_sl_url'] ) && is_array( $_POST['ng_sl_url'] ) ? wp_unslash( $_POST['ng_sl_url'] ) : array(); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		list( $links, $skipped ) = self::clean_rows( $titles, $urls );

		$current = get_post_meta( $episode_id, 'ng_story_links', true );
		if ( $links !== $current ) {
			update_post_meta( $episode_id, 'ng_story_links', $links );
		}
		$script = (string) get_post_meta( $episode_id, 'ng_script_final', true );
		if ( '' !== $script ) {
			$rewritten = self::rewrite_script_links( $script, $links );
			if ( $rewritten !== $script ) {
				update_post_meta( $episode_id, 'ng_script_final', $rewritten );
			}
		}
		$notes = (string) get_post_meta( $episode_id, 'ng_meta_captivate_notes', true );
		if ( '' !== $notes ) {
			$rewritten = self::rewrite_notes_links( $notes, $links );
			if ( $rewritten !== $notes ) {
				update_post_meta( $episode_id, 'ng_meta_captivate_notes', $rewritten );
			}
		}
		if ( $skipped ) {
			set_transient( 'ng_story_links_notice_' . get_current_user_id(), $skipped, 120 );
		}
	}

	public static function notice() {
		$skipped = get_transient( 'ng_story_links_notice_' . get_current_user_id() );
		if ( ! $skipped ) {
			return;
		}
		delete_transient( 'ng_story_links_notice_' . get_current_user_id() );
		printf(
			'<div class="notice notice-warning is-dismissible"><p>%s</p></div>',
			esc_html( sprintf( _n( '%d source story was left out because its address is missing or does not start with http:// or https://.', '%d source stories were left out because their addresses are missing or do not start with http:// or https://.', $skipped, 'net-gain-studio' ), $skipped ) )
		);
	}
}
